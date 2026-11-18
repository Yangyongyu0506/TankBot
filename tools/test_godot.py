#!/usr/bin/env python3
"""Isolated Godot/native-CPython flow, separate from ordinary Python tests."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / path) for path in ('host', 'protocol', 'sdk/python', 'tools')]


def launcher_smoke(binary, isolated, out, env, offline):
    """Exercise the real source launcher and window-exit ownership, on another port."""
    from tankbot_host.configuration import load_yaml
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = load_yaml(ROOT / 'config/game.yaml')
    config['host']['port'] = port
    # Keep JSON's exponent numbers in JSON parsing; YAML 1.1 treats 1e-09 as text.
    path = isolated / 'launcher.json'
    path.write_text(json.dumps(config))
    # Only this isolated fixture injects automatic window closure. Production does not.
    wrapper = isolated / 'godot-auto-close.sh'
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(binary)) + ' --headless --max-fps 60 --quit-after 240 "$@"\n')
    wrapper.chmod(0o755)
    command = [sys.executable, str(ROOT / 'tools/tankbot.py'), '--config', str(path),
               '--godot-binary', str(wrapper), '--workspace-store', str(isolated / 'launcher-workspace'),
               '--settings-file', str(isolated / 'launcher-settings.yaml'), '--save-file', str(isolated / 'launcher-progress.json'),
               *(['--offline'] if offline else [])]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    (out / 'launcher.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and 'SCRIPT ERROR:' not in result.stderr, result.stdout + result.stderr
    try:
        connection = socket.create_connection(('127.0.0.1', port), timeout=1)
    except OSError:
        pass
    else:
        connection.close()
        raise AssertionError('Desktop window exit left HTTP running')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot-binary', type=Path)
    parser.add_argument('--headless', action='store_true', help='No screenshot or real display validation')
    parser.add_argument('--disable-vsync', action='store_true', help='Diagnostic window option for displays with blocked presentation; production settings unchanged')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--real-vscode', action='store_true', help='Open a real isolated VS Code window; default uses a recording launcher')
    parser.add_argument('--vscode-binary', type=Path, help='Explicit VS Code GUI executable for isolated window validation')
    args = parser.parse_args()
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(), offline=args.offline)
    from tankbot_host.authority import Authority, load_config
    from tankbot_host.application import ApplicationState
    from tankbot_host.campaign import configure
    from tankbot_host.desktop import prepare_desktop, settings
    from tankbot_host.server import LocalServer
    binary = prepare_desktop(args.godot_binary, offline=args.offline)
    out = ROOT / '.m1-cache/godot-qa' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    out.mkdir(parents=True)
    config = load_config(ROOT / 'config/game.yaml')
    config['host']['port'] = 0
    with tempfile.TemporaryDirectory(prefix='tankbot-godot-flow-') as temporary:
        isolated = Path(temporary)
        import shutil
        desktop_spec = settings()
        launcher = isolated / 'record-editor.py'
        launcher.write_text('import json,sys\nfrom pathlib import Path\nPath(' + repr(str(out / 'editor-launch.json')) + ').write_text(json.dumps(sys.argv[1:]))\n')
        if args.real_vscode:
            executable = str(args.vscode_binary.resolve()) if args.vscode_binary else shutil.which('code')
            if not executable:
                raise RuntimeError('VS Code is not installed; use --vscode-binary')
            arguments = ['--user-data-dir', str(isolated / 'vscode-profile'), '--extensions-dir', str(isolated / 'vscode-extensions'), '--disable-extensions']
        else:
            executable, arguments = sys.executable, [str(launcher)]
        desktop_spec['editor'].update(executable=executable, arguments=arguments)
        editor_processes = []
        real_popen = subprocess.Popen
        def editor_popen(*values, **keywords):
            process = real_popen(*values, **keywords)
            editor_processes.append(process)
            return process
        editor_settings = patch('tankbot_host.desktop.settings', return_value=desktop_spec)
        editor_launcher = patch('tankbot_host.external_editor.Popen', side_effect=editor_popen)
        editor_settings.start()
        editor_launcher.start()
        app = ApplicationState(config, isolated / 'settings.yaml', isolated / 'progress.json')
        # A legitimate precompleted prerequisite fixture, not a developer grant.
        progress = app.new_progress()
        progress.update(completed_levels=['c0'], current_level='c1',
                        completions={'c0': {'completed_at': datetime.now(timezone.utc).isoformat()}})
        app.write(app.progress_path, app.validate_progress(progress))
        authority = Authority(configure(config, 'c1'))
        server = LocalServer(authority, workspace_store=isolated / 'workspace', application=app)
        service = threading.Thread(target=server.serve)
        service.start()
        client = isolated / 'client.json'
        client.write_text(json.dumps(settings()['client'], ensure_ascii=False))
        env = dict(os.environ)
        for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            env[key] = str(isolated / key.lower())
        command = [str(binary), *(['--headless'] if args.headless else []),
                   *(['--disable-vsync'] if args.disable_vsync else []), '--path', str(ROOT / 'clients/godot'),
                   '--script', 'res://tests/integration.gd', '--',
                   '--backend-url=http://127.0.0.1:' + str(server.http.server_port),
                   '--client-settings=' + str(client), '--report=' + str(out / 'flow.json'),
                   '--screenshot=' + str(out / 'game.png')]
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
            (out / 'godot.log').write_text(result.stdout + result.stderr)
            print(result.stdout + result.stderr)
            assert result.returncode == 0, 'Godot returned a nonzero status'
            report = json.loads((out / 'flow.json').read_text())
            assert report['passed'] and not any('SCRIPT ERROR:' in line for line in result.stderr.splitlines())
            assert app.progress()['completed_levels'] == ['c0', 'c1'], 'Actual pass must persist progress'
            assert not app.developer
            launcher_smoke(binary, isolated, out, env, args.offline)
            if not args.real_vscode:
                assert (out / 'editor-launch.json').is_file(), 'F2 did not invoke the external launcher'
            else:
                assert any(process.poll() is None for process in editor_processes), 'The isolated VS Code GUI exited before flow completion'
            (out / 'editor-evidence.json').write_text(json.dumps({'real_vscode': args.real_vscode,
                'launches': len(editor_processes), 'live_at_end': sum(process.poll() is None for process in editor_processes),
                'saved_file_input': 'integration fixture writes real files; no claim of manual VS Code keystroke/IME validation'}, indent=2))
            print('PASS: external saved files → single Start → C1 pass → retry; source/history/progress preserved.')
            print('PASS: unified godot launcher exits with the window and closes its HTTP backend.')
            print('Evidence:', out.relative_to(ROOT))
            return 0
        finally:
            editor_settings.stop()
            editor_launcher.stop()
            if args.real_vscode:
                for process in editor_processes:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
            server.http.shutdown()
            service.join(timeout=5)
            server.authority.close()
            authority.close()


if __name__ == '__main__':
    raise SystemExit(main())
