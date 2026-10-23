"""M3 preservation, immutable artifacts, lifecycle, grants and fault containment."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'host'), str(ROOT / 'protocol')]
from tankbot_host.authority import Authority, load_config
from tankbot_host.deployment import DeploymentManager, inspect_snapshot
from tankbot_host.workspace import WorkspaceStore, starter, validate_files, read_sources, digest


class WorkspaceFixture:
    def setUp(self):
        self.config = load_config(ROOT / 'config/m1.json')
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(self.temp.name, starter(self.config), self.config['workspace'])

    def tearDown(self):
        self.temp.cleanup()

class WorkspaceTests(WorkspaceFixture, unittest.TestCase):
    def test_templates_preserve_code_and_explicit_merge_keeps_recoverable_revision(self):
        original = self.store.read()
        edited = self.store.edit(original['revision'], {'localization/odometry.py': '# my algorithm\n'})
        plan = self.store.plan('odometry', '1', starter(self.config), edited['revision'])
        merged = self.store.apply(plan['plan_id'], edited['revision'], {})
        self.assertEqual(merged['files']['localization/odometry.py'], '# my algorithm\n')
        self.assertEqual(self.store.read(edited['revision']), edited)
        plan = self.store.plan('odometry', '2', {'localization/odometry.py': '# new template\n'}, merged['revision'])
        replaced = self.store.apply(plan['plan_id'], merged['revision'], {'localization/odometry.py': 'incoming'})
        self.assertEqual(replaced['files']['localization/odometry.py'], '# new template\n')
        self.assertEqual(self.store.read(merged['revision'])['files']['localization/odometry.py'], '# my algorithm\n')

    def test_compare_and_swap_and_failed_head_commit_leave_original(self):
        old = self.store.read()
        plan = self.store.plan('extra', '1', {'extra.py': ''}, old['revision'])
        new = self.store.edit(old['revision'], {'helper.py': ''})
        with self.assertRaisesRegex(ValueError, 'REVISION_CONFLICT'):
            self.store.apply(plan['plan_id'], old['revision'], {})
        with self.assertRaisesRegex(ValueError, 'REVISION_CONFLICT'):
            self.store.edit(old['revision'], {'helper.py': 'changed'})
        with patch('tankbot_host.workspace.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.store.edit(new['revision'], {'extra.py': ''})
        self.assertEqual(self.store.read(), new)

    def test_paths_links_case_collisions_and_limits(self):
        for files in ({'../escape.py': ''}, {'/escape.py': ''}, {'a.py': '', 'A.py': ''}, {'CON.py': ''}, {'a.py': '\0'}, {'x.py': 'x'*40000}, {'a.py/x.py':'', 'a.py':''}):
            with self.subTest(files=list(files)), self.assertRaises(ValueError):
                validate_files(files, self.config['workspace'])
        source = Path(self.temp.name) / 'seed'; source.mkdir()
        (source / 'a.py').write_text('')
        (source / 'link.py').symlink_to(source / 'a.py')
        with self.assertRaisesRegex(ValueError, 'SYMLINK'):
            read_sources(source, self.config['workspace'])
        (source / 'link.py').unlink()
        os.link(source / 'a.py', source / 'hard.py')
        with self.assertRaises(ValueError):
            read_sources(source, self.config['workspace'])

    def test_separate_store_instances_cas_and_untrusted_archives(self):
        other = WorkspaceStore(self.temp.name, starter(self.config), self.config['workspace'])
        old = self.store.read()
        def save(store, name):
            try:
                return store.edit(old['revision'], {name: ''})['revision']
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(save, store, name) for store, name in ((self.store, 'one.py'), (other, 'two.py'))]
            results = [f.result() for f in futures]
        self.assertEqual(sum(r.startswith('REVISION_CONFLICT') for r in results), 1)
        record = {'status': 'Ready', 'sha256': 'untrusted-client-claim'}
        self.store.archive(old['revision'], record)
        self.assertEqual(len(other.archives()), 1)
        self.assertEqual(self.store.read(old['revision']), old)
        self.assertNotIn('tests/test_project.py', other.archives()[0]['files'])


class DeploymentTests(WorkspaceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.authority = Authority(self.config, controlled=True)
        self.manager = DeploymentManager(self.authority)
        self.authority.deployment = self.manager

    def tearDown(self):
        self.authority.close()
        super().tearDown()

    def finish(self):
        deadline = time.monotonic() + 10
        while self.manager.job and time.monotonic() < deadline:
            self.authority.advance()
            if self.manager.job and not self.manager.job['worker'].ready:
                time.sleep(.002)
        self.assertIsNone(self.manager.job, self.manager.status())
        return self.manager.last

    def test_test_deploy_edit_and_explicit_rollback_do_not_reset_world(self):
        snapshot = self.store.read()
        self.manager.start('test', snapshot)
        report = self.finish()
        self.assertEqual(report['status'], 'Ready', report)
        self.assertEqual(report['unit_tests'], 1)
        self.manager.start('deploy', snapshot)
        self.assertEqual(self.finish()['status'], 'Active')
        first = copy.deepcopy(self.manager.active)
        worker = self.authority.worker
        run_id = self.authority.run_id
        tick = self.authority.tick
        edited = self.store.edit(snapshot['revision'], {'helper.py': 'VALUE = 1\n'})
        self.assertIs(self.authority.worker, worker)
        with self.assertRaisesRegex(ValueError, 'TEST_REQUIRED'):
            self.manager.start('deploy', edited)
        self.manager.start('test', edited)
        self.assertEqual(self.finish()['status'], 'Ready')
        self.manager.start('deploy', edited)
        self.assertEqual(self.finish()['status'], 'Active')
        self.assertNotEqual(self.manager.active['sha256'], first['sha256'])
        self.manager.start('rollback', sha256=first['sha256'])
        self.assertEqual(self.finish()['status'], 'Active')
        self.assertEqual(self.manager.active['sha256'], first['sha256'])
        self.assertNotEqual(self.manager.active['deployment_id'], first['deployment_id'])
        self.assertEqual(self.authority.run_id, run_id)
        self.assertGreater(self.authority.tick, tick)
        self.assertTrue(all(d['activated_tick'] % self.authority.period == 0 for d in self.manager.history))
        for _ in range(24): self.authority.advance()
        self.assertFalse(self.authority._faulted)

    def test_failed_import_test_loop_and_invalid_outputs_preserve_active(self):
        original = self.store.read()
        worker = self.authority.worker
        for source in ('raise RuntimeError("bad import")\n', 'while True: pass\n'):
            edited = self.store.edit(self.store.read()['revision'], {'localization/odometry.py': source})
            self.manager.start('test', edited)
            last = self.finish()
            self.assertEqual(last['status'], 'Failed', last)
            self.assertIs(self.authority.worker, worker)
        self.store.edit(self.store.read()['revision'], original['files'])
        manifest = json.loads(original['files']['tankbot.json'])
        manifest['modules'][0]['config'] = {'output_frame': 'base_link'}
        edited = self.store.edit(self.store.read()['revision'], {'tankbot.json': json.dumps(manifest)})
        self.manager.start('test', edited)
        self.assertEqual(self.finish()['status'], 'Failed')
        self.assertIs(self.authority.worker, worker)

    def test_syntax_permissions_shadowing_and_stale_report(self):
        snapshot = self.store.read()
        artifact = inspect_snapshot(snapshot, self.authority)
        reordered = copy.deepcopy(snapshot);reordered['files'] = dict(reversed(list(snapshot['files'].items())))
        self.assertEqual(inspect_snapshot(reordered, self.authority)['sha256'], artifact['sha256'])
        for path, source in [('bad.py', 'def broken(:\n'), ('tankbot.py', ''), ('json.py', '')]:
            changed = copy.deepcopy(snapshot);changed['files'][path] = source
            changed['revision'] = digest({'files': changed['files'], 'ledger': changed['ledger']})
            with self.assertRaises(ValueError): inspect_snapshot(changed, self.authority)
        manifest = json.loads(snapshot['files']['tankbot.json']);manifest['pose_source']['mode'] = 'system';manifest['pose_source'].pop('module_id')
        changed = copy.deepcopy(snapshot);changed['files']['tankbot.json'] = json.dumps(manifest)
        changed['revision'] = digest({'files': changed['files'], 'ledger': changed['ledger']})
        with self.assertRaises(ValueError): inspect_snapshot(changed, self.authority)
        self.manager.start('test', snapshot);self.assertEqual(self.finish()['status'], 'Ready')
        self.authority.config['runtime']['batch_budget_ms'] += 1
        with self.assertRaises(ValueError): self.manager.start('deploy', snapshot)

    def test_unit_test_failure_and_failed_staging_keep_previous_runtime(self):
        snapshot = self.store.read()
        worker = self.authority.worker
        bad = self.store.edit(snapshot['revision'], {'tests/test_fail.py': 'import unittest\nclass Failure(unittest.TestCase):\n def test_fail(self): self.fail("intentional")\n'})
        self.manager.start('test', bad);self.assertEqual(self.finish()['status'], 'Failed')
        self.assertIs(worker, self.authority.worker)
        self.manager.start('test', snapshot);self.assertEqual(self.finish()['status'], 'Ready')
        # Same tested artifact; force an external staging crash before its ready handshake.
        self.manager.start('deploy', snapshot)
        self.manager.job['worker'].proc.kill()
        self.assertEqual(self.finish()['status'], 'Failed')
        self.assertIs(worker, self.authority.worker)
        self.assertIsNone(self.manager.active)


if __name__ == '__main__':
    unittest.main()
