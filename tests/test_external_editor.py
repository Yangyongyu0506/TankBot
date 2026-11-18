"""Disk drafts, immutable Start, non-overwrite upgrades and local editor launch."""
import copy
from contextlib import chdir
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ('host', 'protocol', 'sdk/python', 'tests')]
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure
from tankbot_host.server import LocalServer
from tankbot_host.workspace_api import WorkspaceAPI
from campaign_support import TRANSFORMS


class ExternalEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load_config(ROOT / 'config/game.yaml')
        cls.config = configure(cls.base, 'c1')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = WorkspaceAPI(self.config, directory=Path(self.temp.name) / 'store')
        self.api.external.refresh()

    def test_saved_files_capture_only_on_start_and_old_revision_survives(self):
        before = self.api.store.read()
        path = self.api.external.root / 'perception/transforms.py'
        code = '# authored\r\n' + TRANSFORMS
        path.write_bytes(code.encode())
        (self.api.external.root / 'my_notes.py').write_text('# new source\n')
        self.assertEqual(self.api.store.read(), before)
        self.api.external.refresh()  # Opening VS Code must not discard a saved draft.
        self.assertEqual(path.read_bytes(), code.encode())
        captured = self.api.external.capture()
        self.assertEqual(captured['files']['perception/transforms.py'], code)
        self.assertEqual(captured['files']['my_notes.py'], '# new source\n')
        self.assertEqual(self.api.store.read(before['revision']), before)
        self.assertEqual(self.api.external.capture(), captured)
        self.assertEqual(captured['ledger'], before['ledger'])

    def test_new_scaffolding_and_reopen_preserve_uncaptured_code(self):
        path = self.api.external.root / 'perception/transforms.py'
        path.write_text('# not captured yet\n')
        self.api.unlock(configure(self.base, 'c2'))
        self.api.external.refresh()
        self.assertEqual(path.read_text(), '# not captured yet\n')
        self.assertTrue((self.api.external.root / 'perception/tracker.py').is_file())
        reopened = WorkspaceAPI(configure(self.base, 'c1'), directory=self.api.store.directory)
        reopened.external.refresh()
        self.assertEqual(path.read_text(), '# not captured yet\n')
        self.assertEqual(reopened.external.capture()['files']['perception/transforms.py'], '# not captured yet\n')

    def test_conflicting_history_change_never_overwrites_a_disk_draft(self):
        path = self.api.external.root / 'perception/transforms.py'
        path.write_text('# external edit\n')
        before = self.api.store.read()
        head = self.api.store.edit(before['revision'], {'perception/transforms.py': '# other revision\n'})
        with self.assertRaisesRegex(ValueError, 'EDITOR_MERGE_CONFLICT.*perception/transforms.py'):
            self.api.external.capture()
        self.assertEqual(path.read_text(), '# external edit\n')
        self.assertEqual(self.api.store.read(), head)
        self.assertEqual(self.api.store.read(before['revision']), before)

    def test_explicit_update_preserves_old_disk_file_in_recovery(self):
        before = self.api.store.read()
        path = self.api.external.root / 'campaign_robot.py'
        original = path.read_bytes()
        self.api.store.edit(before['revision'], {'campaign_robot.py': '# explicitly updated\n'})
        self.api.external.refresh()
        self.assertEqual(path.read_text(), '# explicitly updated\n')
        self.assertIn(original, [p.read_bytes() for p in self.api.external.recovery.iterdir()])

    def test_editor_save_racing_a_framework_update_is_never_overwritten(self):
        previous = self.api.store.read()
        path = self.api.external.root / 'campaign_robot.py'
        original = path.read_bytes()
        self.api.store.edit(previous['revision'], {'campaign_robot.py': '# framework update\n'})
        rename = Path.rename
        def save_after_move(source, destination):
            result = rename(source, destination)
            if source == path:
                source.write_text('# concurrent external save\n')
            return result
        with patch.object(Path, 'rename', save_after_move):
            with self.assertRaisesRegex(ValueError, 'EDITOR_CONCURRENT_SAVE'):
                self.api.external.refresh()
        self.assertEqual(path.read_text(), '# concurrent external save\n')
        self.assertIn(original, [p.read_bytes() for p in self.api.external.recovery.iterdir()])

    def test_upgrade_requires_preview_and_rejects_saved_changes_after_preview(self):
        path = self.api.external.root / 'perception/transforms.py'
        path.write_text(TRANSFORMS)
        self.api.unlock(configure(self.base, 'c2'))
        plan = self.api.post('external_upgrade', {})
        self.assertNotIn('perception/transforms.py', [e['path'] for e in plan['entries']])
        (self.api.external.root / 'my_notes.py').write_text('# changed during preview\n')
        value = {'revision': plan['base_revision'], 'plan_id': plan['plan_id'],
                 'resolutions': {e['path']: 'incoming' for e in plan['entries']}}
        with self.assertRaisesRegex(ValueError, 'REVISION_CONFLICT'):
            self.api.post('external_apply', value)
        plan = self.api.post('external_upgrade', {})
        result = self.api.post('external_apply', {'revision': plan['base_revision'], 'plan_id': plan['plan_id'],
                        'resolutions': {e['path']: 'incoming' for e in plan['entries']}})
        self.assertEqual(result['files']['perception/transforms.py'], TRANSFORMS)
        self.assertEqual(path.read_text(), TRANSFORMS)
        self.assertEqual(result['files']['my_notes.py'], '# changed during preview\n')

    def test_failed_metadata_commit_does_not_lose_saved_source_or_history(self):
        before = self.api.store.read()
        path = self.api.external.root / 'my_notes.py'
        path.write_text('# survives interrupted capture\n')
        with patch.object(self.api.external, '_record', side_effect=[None, OSError('fixture interruption')]):
            with self.assertRaises(OSError):
                self.api.external.capture()
        self.assertEqual(self.api.store.read()['files']['my_notes.py'], path.read_text())
        self.assertEqual(self.api.store.read(before['revision']), before)
        self.assertEqual(self.api.external.capture()['files']['my_notes.py'], path.read_text())

    def test_visible_links_and_oversized_or_deep_sources_are_rejected(self):
        outside = Path(self.temp.name) / 'outside.py'
        outside.write_text('# outside\n')
        linked = self.api.external.root / 'linked.py'
        if os.name != 'nt':
            linked.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'UNSAFE_EDITOR_PATH'):
                self.api.external.capture()
            linked.unlink()
            os.link(outside, linked)
            with self.assertRaisesRegex(ValueError, 'UNSAFE_EDITOR_PATH'):
                self.api.external.capture()
            linked.unlink()
        linked.write_text('x' * (self.config['workspace']['max_source_bytes'] + 1))
        with self.assertRaisesRegex(ValueError, 'WORKSPACE_BYTE_LIMIT'):
            self.api.external.capture()
        linked.unlink()
        self.api.external.options = {**self.api.external.options, 'max_scan_depth': 2}
        path = self.api.external.root / 'one/two/three/code.py'
        path.parent.mkdir(parents=True)
        path.write_text('')
        with self.assertRaisesRegex(ValueError, 'EDITOR_TREE_LIMIT'):
            self.api.external.capture()

    def test_launch_is_shell_free_and_opens_only_current_project_and_lesson_files(self):
        with patch('tankbot_host.external_editor.shutil.which', return_value='/path with spaces/code'), \
                patch('tankbot_host.external_editor.Popen', return_value=Mock()) as launch:
            result = self.api.post('external_open', {})
        command = launch.call_args.args[0]
        self.assertEqual(command[0], '/path with spaces/code')
        self.assertIn(str(self.api.external.root), command)
        self.assertIn(str(self.api.external.root / 'perception/transforms.py'), command)
        self.assertFalse(launch.call_args.kwargs.get('shell', False))
        self.assertTrue(result['requested'])
        self.assertNotIn('.vscode/settings.json', self.api.external.capture()['files'])
        for operation in ('external_open', 'external_upgrade'):
            with self.assertRaisesRegex(ValueError, 'INVALID_EDITOR_REQUEST'):
                self.api.post(operation, {'path': '/etc/passwd', 'arguments': ['--anything']})

    def test_missing_vscode_keeps_source_and_reports_editable_directory(self):
        before = self.api.store.read()
        with patch('tankbot_host.external_editor.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'VSCODE_NOT_FOUND.*代码目录'):
                self.api.post('external_open', {})
        self.assertEqual(self.api.store.read(), before)

    def test_relative_store_and_spaced_parent_open_absolute_editor_paths(self):
        with chdir(self.temp.name):
            api = WorkspaceAPI(self.config, directory='my project')
            with patch('tankbot_host.external_editor.shutil.which', return_value='/bin/code'), \
                    patch('tankbot_host.external_editor.Popen', return_value=Mock()) as launch:
                value = api.post('external_open', {})
            self.assertTrue(Path(value['directory']).is_absolute())
            self.assertIn(str(Path(self.temp.name) / 'my project/files'), launch.call_args.args[0])


class SingleStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = configure(load_config(ROOT / 'config/game.yaml'), 'c1')
        config['host']['port'] = 0
        authority = Authority(config)
        self.server = LocalServer(authority, workspace_store=Path(self.temp.name) / 'store')
        self.thread = threading.Thread(target=self.server.serve)
        self.thread.start()
        self.addCleanup(self.close)
        self.server.workspace.external.refresh()

    def close(self):
        self.server.http.shutdown()
        self.thread.join(5)
        self.server.authority.close()

    def request(self, path, payload=None, authorized=True):
        port = self.server.http.server_port
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers.update(Origin=f'http://127.0.0.1:{port}', **{'X-TankBot-Control': self.server.token})
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        connection.request('POST' if payload is not None else 'GET', path,
                           json.dumps(payload) if payload is not None else None, headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_start_freezes_saved_revision_checks_and_runs_without_manual_deploy(self):
        api = self.server.workspace
        path = api.external.root / 'perception/transforms.py'
        path.write_text(TRANSFORMS)
        before = api.store.read()
        code, value = self.request('/api/campaign/run', {'level_id': 'c1'})
        self.assertEqual(code, 200, value)
        self.assertEqual(value['player_start']['phase'], 'Checking', value)
        revision = value['player_start']['revision']
        self.assertNotEqual(revision, before['revision'])
        until = time.monotonic() + 15
        while time.monotonic() < until:
            _, status = self.request('/api/deployment')
            if status['player_start']['phase'] in ('Running', 'Failed'):
                break
            time.sleep(.05)
        self.assertEqual(status['player_start']['phase'], 'Running', status)
        self.assertEqual(status['active']['revision'], revision)
        path.write_text('def broken(:\n')
        self.assertEqual(self.server.authority.deployment.active['revision'], revision)
        self.assertEqual(api.store.read()['revision'], revision)
        self.assertEqual(self.request('/api/campaign/run', {'level_id': 'c1'})[0], 400)
        self.request('/api/campaign/finish', {})
        code, failure = self.request('/api/campaign/run', {'level_id': 'c1'})
        self.assertEqual(code, 200)
        self.assertEqual(failure['player_start']['phase'], 'Failed', failure)
        self.assertIn('SyntaxError', failure['player_start']['error'])
        self.assertIsNone(self.server.authority.deployment.active)
        self.assertEqual(api.store.read(before['revision']), before)

    def test_new_management_operations_keep_authentication_and_strict_arguments(self):
        for path in ('/api/workspace/external_open', '/api/campaign/run'):
            payload = {} if path.endswith('external_open') else {'level_id': 'c1'}
            self.assertEqual(self.request(path, payload, authorized=False)[0], 403)
        self.assertEqual(self.request('/api/campaign/run', {'level_id': 'c1', 'sources': {}})[0], 400)
        code, result = self.request('/api/campaign/run', {'level_id': 'c0'})
        self.assertEqual(code, 200, result)
        self.assertIsNone(result['player_start'])  # The passive manual lesson needs no player algorithm.

    def test_stop_during_preflight_cancels_automatic_activation(self):
        (self.server.workspace.external.root / 'perception/transforms.py').write_text(TRANSFORMS)
        self.assertEqual(self.request('/api/campaign/run', {'level_id': 'c1'})[0], 200)
        self.request('/api/campaign/finish', {})
        until = time.monotonic() + 5
        while time.monotonic() < until and self.server.player_run.phase != 'Cancelled':
            time.sleep(.01)
        self.assertEqual(self.server.player_run.phase, 'Cancelled')
        self.assertIsNone(self.server.authority.deployment.active)
        self.assertIsNone(self.server.authority.deployment.job)
        self.assertIsNone(self.server.authority.campaign.started_tick)

    def test_missing_manifest_reports_start_failure_without_losing_new_run_identity(self):
        (self.server.workspace.external.root / 'tankbot.json').unlink()
        code, result = self.request('/api/campaign/run', {'level_id': 'c1'})
        self.assertEqual(code, 200, result)
        self.assertEqual(result['player_start']['phase'], 'Failed')
        self.assertIn('tankbot.json', result['player_start']['error'])
        self.assertEqual(result['profile']['run_id'], self.request('/api/profile')[1]['run_id'])
        self.assertIsNone(self.server.authority.deployment.active)

    def test_single_start_also_performs_independent_planning_and_formal_activation(self):
        from planning_support import solution
        with self.server.lock:
            self.server.start_level('navigation.c5')
            api = self.server.workspace
            api.external.refresh()
            for name, source in solution(self.server.authority.config).items():
                path = api.external.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
        code, value = self.request('/api/campaign/run', {'level_id': 'navigation.c5'})
        self.assertEqual(code, 200, value)
        until = time.monotonic() + 20
        while time.monotonic() < until:
            _, status = self.request('/api/deployment')
            if status['player_start']['phase'] in ('Running', 'Failed'):
                break
            time.sleep(.05)
        self.assertEqual(status['player_start']['phase'], 'Running', status)
        self.assertIsNotNone(self.server.authority.campaign.navigation.reference)
        self.assertEqual(len(self.server.authority.deployment.reports), 1)
        self.assertEqual(self.server.authority.runtime_profile.batch_wall_deadline_ms, 30)
        self.assertEqual(self.server.authority.runtime_profile.module_declared_budget_cap_ms, 20)


if __name__ == '__main__':
    unittest.main()
