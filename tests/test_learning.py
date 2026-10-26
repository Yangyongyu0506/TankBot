"""Teaching contracts, SE(3) mathematics, metadata and non-overwriting upgrades."""
import ast
from dataclasses import fields, is_dataclass
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python")]
import tankbot
from tankbot import Pose2D, RadarDetection
from tankbot.transforms import radar_point, validate_se3
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure
from tankbot_host.learning import learning_bundle
from tankbot_host.workspace import WorkspaceStore, starter
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.deployment import inspect_snapshot, DeploymentManager
from tankbot_host.campaign_templates import WRAPPER, framework_upgrade, MANAGED_FILES
from campaign_support import TRANSFORMS, solutions


class LearningTests(unittest.TestCase):
    def config(self, level="c1"):
        return configure(load_config(ROOT / "config/game.yaml"), level)

    def test_every_level_has_guidance_and_generated_python_has_explicit_types(self):
        for level in ("c0", "c1", "c2", "c3", "c4", "c5"):
            config = self.config(level)
            guide = learning_bundle(config)
            self.assertTrue(guide["lesson"]["steps"])
            for key in ("completion", "execution", "common_errors"):
                self.assertTrue(guide["lesson"][key], (level, key))
            if level != "c0":
                self.assertTrue(guide["lesson"]["functions"])
                self.assertTrue(guide["lesson"]["files"])
            for path, source in starter(config).items():
                if not path.endswith(".py"):
                    continue
                tree = ast.parse(source)
                declared = {ast.unparse(node.target) for node in ast.walk(tree) if isinstance(node, ast.AnnAssign)}
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        self.assertIsNotNone(node.returns, (level, path, node.name))
                        for arg in node.args.args:
                            if arg.arg != "self":
                                self.assertIsNotNone(arg.annotation, (path, arg.arg))
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, (ast.Name, ast.Attribute)):
                                self.assertIn(ast.unparse(target), declared, (path, ast.unparse(target)))
            encoded = json.dumps(guide)
            for secret in ("waypoints_m", "target_id", "truth_pose", "core_call"):
                self.assertNotIn(secret, encoded)

    def test_type_reference_matches_real_sdk_fields(self):
        guide = learning_bundle(self.config())
        for item in guide["types"]:
            if item["name"] == "ndarray":
                continue
            cls = getattr(tankbot, item["name"])
            if is_dataclass(cls):
                self.assertEqual([f.name for f in fields(cls)], [f["name"] for f in item["fields"]])
            self.assertTrue(item["description"])
            self.assertTrue(all(field["description"] and field["type"] for field in item["fields"]))
        signature = guide["lesson"]["functions"][0]["signature"]
        self.assertEqual(signature, "radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]")

    def test_se3_matrix_transforms_points_and_directions_and_is_invertible(self):
        namespace = {}
        exec(TRANSFORMS, namespace)
        own_pose = Pose2D(1, 3, math.pi/2)
        matrix = validate_se3(namespace["radar_to_map"](own_pose), tolerance=1e-8)
        point = radar_point(RadarDetection("synthetic", 2, 0))
        np.testing.assert_allclose(matrix @ point, [1, 5, 0, 1], atol=1e-8)
        np.testing.assert_allclose(matrix @ np.array([2, 0, 0, 0]), [0, 2, 0, 0], atol=1e-8)
        np.testing.assert_allclose(np.linalg.inv(matrix) @ (matrix @ point), point, atol=1e-8)
        self.assertEqual(matrix.shape, (4, 4))
        self.assertEqual(matrix.dtype, np.float64)

    def test_se3_rejects_lists_wrong_shape_nonfinite_scaling_reflection_and_last_row(self):
        bad = [np.eye(4).tolist(), np.eye(3), np.eye(4, dtype=complex), np.full((4, 4), np.nan)]
        scaled = np.eye(4); scaled[0, 0] = 2
        reflected = np.eye(4); reflected[0, 0] = -1
        last_row = np.eye(4); last_row[3, 0] = 1
        for matrix in [*bad, scaled, reflected, last_row]:
            with self.assertRaises((TypeError, ValueError)):
                validate_se3(matrix, tolerance=1e-8)

    def test_player_matrix_is_actually_used_in_the_live_pipeline(self):
        config = self.config()
        source = solutions(config)
        source["perception/transforms.py"] = '''import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D
def radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:
    matrix: NDArray[np.float64] = np.eye(4, dtype=np.float64)
    matrix[:2, 3] = [2.0, 3.0]
    return matrix
'''
        a = Authority(config, controlled=True, startup_sources=source)
        self.addCleanup(a.close)
        for _ in range(30):
            a.advance()
        self.assertIsNotNone(a._target_estimate)
        estimate = a._target_estimate["payload"]
        np.testing.assert_allclose([estimate["x_m"], estimate["y_m"]], [-1, 4.5], atol=1e-8)
        self.assertEqual(a._private["truth_pose"], [0, 0, 0])
        self.assertEqual(a._private["targets"][0]["pose"], config["weapons"]["targets"][0]["pose"])

    def test_upgrade_preview_preserves_algorithms_and_history(self):
        config = self.config()
        old_files = starter(config)
        old_files.pop("perception/transforms.py")
        old_files["campaign_robot.py"] = "# previous framework\n"
        old_files["perception/coordinates.py"] = "# player's previous algorithm\n"
        with tempfile.TemporaryDirectory() as directory:
            original = WorkspaceStore(directory, old_files, config["workspace"]).read()
            api = WorkspaceAPI(config, directory=directory)
            current = api.get()
            self.assertTrue(current["learning"]["upgrade_required"])
            self.assertEqual(current["snapshot"]["files"]["campaign_robot.py"], old_files["campaign_robot.py"])
            with self.assertRaisesRegex(ValueError, "TEACHING_TEMPLATE_UPGRADE_REQUIRED"):
                inspect_snapshot(current["snapshot"], SimpleNamespace(config=config))
            plan = api.post("template", {"revision": current["snapshot"]["revision"]})
            managed = set(current["learning"]["managed_files"])
            resolutions = {entry["path"]: "incoming" if entry["path"] in managed else "keep" for entry in plan["entries"]}
            upgraded = api.post("apply", {"revision": plan["base_revision"], "plan_id": plan["plan_id"], "resolutions": resolutions})
            self.assertEqual(upgraded["files"]["perception/coordinates.py"], old_files["perception/coordinates.py"])
            self.assertFalse(api.get()["learning"]["upgrade_required"])
            self.assertEqual(api.store.read(original["revision"])["files"], old_files)

    def test_guided_upgrade_only_replaces_framework_and_can_test_saved_algorithm(self):
        config = self.config()
        old_files = solutions(config)
        old_files["campaign_robot.py"] = "# old teaching wrapper\n"
        old_files["perception/coordinates.py"] = "# preserved old solution\n"
        old_files["tests/test_player_algorithm.py"] = "# user tests\n"
        with tempfile.TemporaryDirectory() as directory:
            before = WorkspaceStore(directory, old_files, config["workspace"]).read()
            api = WorkspaceAPI(config, directory=directory)
            plan = api.post("upgrade", {"revision": api.get()["snapshot"]["revision"]})
            self.assertEqual(plan["purpose"], "teaching-framework-upgrade")
            self.assertTrue(all(entry["path"] in MANAGED_FILES for entry in plan["entries"]))
            self.assertTrue(api.get()["learning"]["upgrade_required"], "preview must not modify sources")
            upgraded = api.post("apply", {"revision": plan["base_revision"], "plan_id": plan["plan_id"],
                                          "resolutions": {entry["path"]: "incoming" for entry in plan["entries"]}})
            for path, source in before["files"].items():
                if path not in MANAGED_FILES:
                    self.assertEqual(upgraded["files"][path], source)
            self.assertEqual(api.store.read(before["revision"])["files"], before["files"])
            self.assertFalse(api.get()["learning"]["upgrade_required"])
            a = Authority(config, controlled=True)
            a.deployment = DeploymentManager(a)
            self.addCleanup(a.close)
            self.assertEqual(inspect_snapshot(upgraded, a)["revision"], upgraded["revision"])
            a.deployment.start("test", snapshot=upgraded)
            for _ in range(180):
                a.advance()
                if a.deployment.last:
                    break
            self.assertEqual(a.deployment.last["status"], "Ready", a.deployment.last)

    def test_framework_comments_are_not_a_version_contract_and_syntax_errors_stay_syntax_errors(self):
        config = self.config()
        for source in ("# my note\n" + WRAPPER, "\n".join(WRAPPER.splitlines()[1:])):
            self.assertFalse(framework_upgrade(config, {"campaign_robot.py": source})["required"])
        files = solutions(config)
        files["campaign_robot.py"] = "def broken(:\n"
        self.assertFalse(framework_upgrade(config, files)["required"])
        snapshot = {"files": files, "ledger": {}}
        from tankbot_host.workspace import digest
        snapshot["revision"] = digest(snapshot)
        with self.assertRaisesRegex(ValueError, 'File "campaign_robot.py", line 1'):
            inspect_snapshot(snapshot, SimpleNamespace(config=config))


if __name__ == "__main__":
    unittest.main()
