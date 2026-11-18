"""Desktop lifecycle adapter. Player Python stays in the existing supervised worker."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def settings():
    from .configuration import load_yaml
    from .resources import repository_path
    from jsonschema import Draft202012Validator
    value = load_yaml(ROOT / 'assets/config/desktop.yaml')
    schema = json.loads((ROOT / 'assets/schemas/desktop.schema.json').read_text())
    Draft202012Validator(schema).validate(value)
    appearance = load_yaml(repository_path(value.get('theme_file', 'assets/config/desktop-theme.yaml')))
    theme_schema = json.loads((ROOT / 'assets/schemas/desktop-theme.schema.json').read_text())
    Draft202012Validator(theme_schema).validate(appearance)
    value['client']['appearance'] = appearance
    sprites = load_yaml(repository_path(value.get('sprites_file', 'assets/config/desktop-sprites.yaml')))
    sprite_schema = json.loads((ROOT / 'assets/schemas/desktop-sprites.schema.json').read_text())
    Draft202012Validator(sprite_schema).validate(sprites)
    for name, definition in sprites['assets'].items():
        relative = definition['path']
        asset = (ROOT / relative).resolve()
        if not asset.is_relative_to((ROOT / 'assets/sprites').resolve()) or not asset.is_file():
            raise ValueError(f'SPRITE_ASSET_MISSING: {name}: {relative}')
        if asset.stat().st_size > sprites['limits']['max_file_bytes']:
            raise ValueError(f'SPRITE_ASSET_TOO_LARGE: {name}: {relative}')
        definition['path'] = str(asset)
    value['client']['sprites'] = sprites
    controls = load_yaml(repository_path(value.get('tools_file', 'assets/config/desktop-tools.yaml')))
    controls_schema = json.loads((ROOT / 'assets/schemas/desktop-tools.schema.json').read_text())
    Draft202012Validator(controls_schema).validate(controls)
    value['client']['tools'] = controls
    return value


def checked_binary(path):
    path = Path(path).resolve()
    result = subprocess.run([str(path), '--version'], capture_output=True, text=True, timeout=10, check=True)
    if not result.stdout.strip().startswith('4.'):
        raise ValueError('桌面原型需要 Godot 4 标准版。')
    return path


def prepare_desktop(explicit=None, *, offline=False, core_binary=None):
    """Reuse system Godot or provision one pinned portable Linux binary. No npm/Web build."""
    spec = settings()['engine']
    found = explicit or shutil.which('godot4') or shutil.which('godot')
    if found:
        binary = checked_binary(found)
    else:
        if (sys.platform, platform.machine()) != ('linux', 'x86_64'):
            raise ValueError('自动准备目前仅支持 Linux x86_64；请用 --godot-binary 指定已安装的 Godot 4。')
        artifact = spec['linux_x86_64']
        cache = ROOT / '.m1-cache/godot' / spec['version']
        binary = cache / artifact['executable']
        if not binary.is_file():
            if offline:
                raise ValueError('离线 Godot 缓存缺失；请联网启动一次或指定 --godot-binary。')
            cache.mkdir(parents=True, exist_ok=True)
            print('准备锁定的 Godot 桌面运行环境…', flush=True)
            # Independent temporary files prevent partial downloads becoming runnable cache entries.
            with tempfile.TemporaryDirectory(dir=cache) as directory:
                archive = Path(directory) / 'godot.zip'
                digest = hashlib.sha512()
                size = 0
                with urlopen(artifact['url'], timeout=60) as source, archive.open('wb') as target:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > artifact['max_archive_bytes']:
                            raise ValueError('Godot 下载超过容量上限。')
                        digest.update(chunk)
                        target.write(chunk)
                if digest.hexdigest() != artifact['archive_sha512']:
                    raise ValueError('Godot SHA-512 校验失败；未安装下载内容。')
                with zipfile.ZipFile(archive) as bundle:
                    # Read one known member: never extract arbitrary paths from an archive.
                    with bundle.open(artifact['executable']) as source:
                        staged = Path(directory) / 'engine'
                        with staged.open('wb') as target:
                            shutil.copyfileobj(source, target)
                staged.chmod(0o755)
                checked_binary(staged)
                os.replace(staged, binary)
        binary = checked_binary(binary)
    if core_binary is None and not (ROOT / 'target/debug/core_worker').is_file():
        subprocess.run([sys.executable, str(ROOT / 'tools/build.py'), '--core-only',
                        *(['--offline'] if offline else [])], cwd=ROOT, check=True)
    return binary


def run_desktop(server, binary):
    """Own both processes; closing the window stops HTTP, physics and all player workers."""
    client = settings()['client']
    host, port = server.http.server_address
    with tempfile.TemporaryDirectory(prefix='tankbot-desktop-') as directory:
        config = Path(directory) / 'client.json'
        config.write_text(json.dumps(client, ensure_ascii=False), encoding='utf-8')
        config.chmod(0o600)
        command = [str(binary), '--path', str(ROOT / 'clients/godot'), '--',
                   '--backend-url=' + f'http://{host}:{port}', '--client-settings=' + str(config)]
        process = None
        service = threading.Thread(target=server.serve, name='tankbot-desktop-host')
        service.start()
        try:
            process = subprocess.Popen(command, cwd=ROOT)
            code = process.wait()
            if code:
                raise ValueError(f'Godot 客户端退出，状态码 {code}。')
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=client['shutdown_timeout_s'])
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            server.http.shutdown()
            service.join(timeout=client['shutdown_timeout_s'])
            server.authority.close()
