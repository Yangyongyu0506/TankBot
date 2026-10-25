"""Persistent userdata location and non-destructive migration of legacy code stores."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("host", "protocol", "sdk/python")]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.workspace import WorkspaceStore, digest, open_store, starter
from tankbot_host.workspace_api import WorkspaceAPI


class WorkspaceStorageTests(unittest.TestCase):
    def setUp(self):
        self.config = configure(load_config(ROOT / "config/game.yaml"), "c1")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch("tankbot_host.workspace.ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.files = starter(self.config)
        self.key = digest({"seed":"default", "entry":self.config["module"]["entry_point"],
                           "sources":self.config["control_sources"]})[:16]
        self.destination = self.root / self.config["workspace"]["storage"]["directory"] / self.key
        self.legacy = self.root / self.config["workspace"]["storage"]["legacy_directory"] / self.key

    def old_store(self):
        store = WorkspaceStore(self.legacy,self.files,self.config["workspace"])
        first = store.read()
        plan = store.plan("player-helper","1",{"helper.py":"VALUE: int = 1\n"},first["revision"])
        store.apply(plan["plan_id"],first["revision"],{})
        current = store.read()
        store.edit(current["revision"],{"perception/transforms.py":"# 我的算法，完整保留\n"})
        store.archive(first["revision"],{"status":"Ready","note":"historical test"})
        return store

    def json_bytes(self, directory):
        return {p.name:p.read_bytes() for p in directory.glob("*.json")}

    def test_new_projects_are_saved_in_userdata_and_reopen_across_levels(self):
        api = WorkspaceAPI(self.config)
        self.assertEqual(api.store.directory,self.destination)
        current = api.get()["snapshot"]
        api.post("save",{"revision":current["revision"],"changes":{"perception/transforms.py":"# player algorithm\n"}})
        config = configure(self.config,"c2")
        reopened = WorkspaceAPI(config)
        self.assertEqual(reopened.store.directory,self.destination)
        self.assertEqual(reopened.get()["snapshot"]["files"]["perception/transforms.py"],"# player algorithm\n")
        self.assertFalse(self.legacy.exists())

    def test_migration_preserves_every_revision_ledger_and_archive_byte_for_byte(self):
        old = self.old_store()
        expected = old.read()
        before = self.json_bytes(self.legacy)
        new = open_store(self.config)
        self.assertEqual(new.read(),expected)
        self.assertEqual(new.archives(),old.archives())
        self.assertEqual(self.json_bytes(self.destination),before)
        self.assertEqual(self.json_bytes(self.legacy),before)
        self.assertTrue(new.read()["ledger"]["player-helper"])
        for p in self.legacy.glob("*.json"):
            if len(p.stem)==64:self.assertEqual(new.read(p.stem),old.read(p.stem))

    def test_existing_destination_wins_without_merging_or_overwriting(self):
        old = self.old_store()
        new = WorkspaceStore(self.destination,self.files,self.config["workspace"])
        snapshot = new.read()
        new.edit(snapshot["revision"],{"helper.py":"# newest userdata version\n"})
        before_new,before_old = self.json_bytes(self.destination),self.json_bytes(self.legacy)
        reopened = open_store(self.config)
        self.assertEqual(reopened.read()["files"]["helper.py"],"# newest userdata version\n")
        self.assertEqual(self.json_bytes(self.destination),before_new)
        self.assertEqual(self.json_bytes(self.legacy),before_old)

    def test_inactive_profiles_migrate_without_being_merged_into_current_project(self):
        self.old_store()
        inactive = self.legacy.parent / ('f'*16 if self.key != 'f'*16 else 'a'*16)
        other = WorkspaceStore(inactive,{"other.py":"# separate player project\n"},self.config["workspace"])
        expected = other.read()
        current = open_store(self.config)
        restored = WorkspaceStore(self.destination.parent/inactive.name,self.files,self.config["workspace"])
        self.assertEqual(restored.read(),expected)
        self.assertNotIn("other.py",current.read()["files"])
        self.assertTrue(inactive.exists())

    def test_corrupt_history_aborts_without_publishing_or_changing_old_code(self):
        old = self.old_store()
        current = old.read()["revision"]
        historical = next(p for p in self.legacy.glob("*.json") if len(p.stem)==64 and p.stem!=current)
        historical.write_text('{}')
        before = self.json_bytes(self.legacy)
        with self.assertRaises((ValueError,KeyError)):
            open_store(self.config)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.json_bytes(self.legacy),before)
        self.assertFalse(list(self.destination.parent.glob('.*-migrating-*')))

    def test_missing_head_and_symlinks_do_not_generate_a_replacement_project(self):
        self.legacy.mkdir(parents=True)
        (self.legacy/'player.py').write_text('# preserve\n')
        with self.assertRaisesRegex(ValueError,'INVALID_LEGACY_WORKSPACE'):
            open_store(self.config)
        self.assertFalse((self.legacy/'HEAD.json').exists())
        self.assertFalse(self.destination.exists())
        self.old_store()
        (self.legacy/'linked.py').symlink_to(self.legacy/'player.py')
        with self.assertRaisesRegex(ValueError,'UNSAFE_LEGACY_WORKSPACE_FILE'):
            open_store(self.config)
        self.assertFalse(self.destination.exists())
        self.assertEqual((self.legacy/'player.py').read_text(),'# preserve\n')

    def test_failed_publication_is_retryable_and_leaves_no_partial_destination(self):
        self.old_store()
        before = self.json_bytes(self.legacy)
        with patch('tankbot_host.workspace.Path.rename',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):open_store(self.config)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.json_bytes(self.legacy),before)
        self.assertFalse(list(self.destination.parent.glob('.*-migrating-*')))
        self.assertEqual(open_store(self.config).read()["files"]["perception/transforms.py"],"# 我的算法，完整保留\n")

    def test_concurrent_launchers_publish_once_and_read_the_same_snapshot(self):
        self.old_store()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(open_store,self.config) for _ in range(2)]
            stores = [f.result() for f in futures]
        self.assertEqual(stores[0].read(),stores[1].read())
        self.assertEqual(self.json_bytes(self.destination),self.json_bytes(self.legacy))

    def test_explicit_store_and_seed_remain_explicit_and_read_only(self):
        self.old_store()
        seed = self.root/'seed';seed.mkdir()
        (seed/'helper.py').write_text('VALUE: int = 7\n')
        chosen = self.root/'chosen-store'
        new = open_store(self.config,seed,chosen)
        self.assertEqual(new.directory,chosen)
        self.assertEqual(new.read()["files"]["helper.py"],'VALUE: int = 7\n')
        self.assertEqual([p.name for p in seed.iterdir()],['helper.py'])
        self.assertFalse(self.destination.parent.exists())
        self.assertTrue(self.legacy.exists())
