"""Independent course projects never import or modify an earlier course's source."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("host", "protocol", "sdk/python")]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.configuration import load_yaml
from tankbot_host.workspace import digest, open_store, workspace_scope
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_protocol.validation import Validator, Rejected


class WorkspaceScopeTests(unittest.TestCase):
    def setUp(self):
        self.config = configure(load_config(ROOT / "config/game.yaml"), "c2")
        self.navigation = copy.deepcopy(self.config)
        # Test storage independently of an unconfirmed new physics/lesson model.
        self.navigation["campaign"]["levels"]["c2"]["scaffolding"]["workspace_scope"] = "navigation"
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch("tankbot_host.workspace.ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_original_campaign_key_and_authored_code_survive_separate_course(self):
        weapons = open_store(self.config)
        original = weapons.read()
        weapons.edit(original["revision"], {"perception/tracker.py": "# authored KF; preserve exactly\n"})
        before = {p.name: p.read_bytes() for p in weapons.directory.glob("*.json")}
        self.assertEqual(weapons.directory.name, digest({"seed": "default", "scope": "campaign"})[:16])
        navigation_sources = {"control.py": "# independent controller\n"}
        with patch("tankbot_host.workspace.starter", return_value=navigation_sources):
            navigation = open_store(self.navigation)
            self.assertEqual(navigation.read()["files"], navigation_sources)
            self.assertEqual(navigation.directory.name, digest({"seed": "default", "scope": "navigation"})[:16])
            current = navigation.read()
            navigation.edit(current["revision"], {"control.py": "# authored drive controller\n"})
            restarted = open_store(self.navigation)
            self.assertEqual(restarted.read()["files"]["control.py"], "# authored drive controller\n")
        self.assertEqual(open_store(self.config).directory, weapons.directory)
        self.assertEqual({p.name: p.read_bytes() for p in weapons.directory.glob("*.json")}, before)

    def test_unlock_refuses_cross_scope_before_writing_any_files(self):
        api = WorkspaceAPI(self.config)
        before = {p.name: p.read_bytes() for p in api.store.directory.glob("*.json")}
        with self.assertRaisesRegex(ValueError, "WORKSPACE_SCOPE_MISMATCH"):
            api.unlock(self.navigation)
        self.assertEqual({p.name: p.read_bytes() for p in api.store.directory.glob("*.json")}, before)
        self.assertEqual(workspace_scope(api.config), "campaign")

    def test_new_course_does_not_inspect_or_copy_unrelated_legacy_projects(self):
        legacy=self.root/self.config["workspace"]["storage"]["legacy_directory"]/('a'*16)
        legacy.mkdir(parents=True)
        (legacy/'HEAD.json').write_text('{broken historical project')
        with patch("tankbot_host.workspace.starter",return_value={"control.py":"# new course\n"}):
            nav=open_store(self.navigation)
        self.assertEqual(nav.read()["files"],{"control.py":"# new course\n"})
        self.assertFalse((nav.directory.parent/legacy.name).exists())
        self.assertEqual((legacy/'HEAD.json').read_text(),'{broken historical project')

    def test_scope_is_schema_checked_and_never_a_path(self):
        validator = Validator(self.config, "scope-test")
        value = load_yaml(ROOT / "levels/hello_robot.C0.yaml")
        value["scaffolding"]["workspace_scope"] = "navigation"
        validator.structure(value, "level.schema.json")
        for invalid in ("../navigation", "/tmp/nav", "", "a" * 49, 1):
            with self.subTest(scope=invalid):
                value["scaffolding"]["workspace_scope"] = invalid
                with self.assertRaises(Rejected):
                    validator.structure(value, "level.schema.json")
                self.navigation["campaign"]["levels"]["c2"]["scaffolding"]["workspace_scope"] = invalid
                with self.assertRaisesRegex(ValueError, "INVALID_WORKSPACE_SCOPE"):
                    open_store(self.navigation)

    def test_navigation_is_a_distinct_chapter_with_a_stable_level(self):
        chapters = self.config["campaign"]["chapters"]
        navigation = next(c for c in chapters if c["chapter_id"] == "navigation")
        self.assertEqual(navigation["title"], "Navigation")
        self.assertEqual(navigation["levels"], ["navigation.c0", "navigation.c1", "navigation.c2", "navigation.c3", "navigation.c4", "navigation.c5", "navigation.c6"])
        self.assertEqual(list(self.config["campaign"]["levels"]), ["c0", "c1", "c2", "c3", "c4", "c5", "navigation.c0", "navigation.c1", "navigation.c2", "navigation.c3", "navigation.c4", "navigation.c5", "navigation.c6"])
