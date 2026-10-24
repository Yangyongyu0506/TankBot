"""Educational dependency grants and NumPy matrix SDK semantics."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python")]
from tankbot import ModuleContext, Pose2D, TargetEstimate
from tankbot._imports import load_policy, validate_imports
from tankbot.transforms import target_positions
from tankbot_host.authority import Authority, load_config
from tankbot_host.deployment import DeploymentManager, inspect_snapshot
from tankbot_host.workspace import starter, digest


class PlayerPolicyTests(unittest.TestCase):
    def test_only_numpy_external_and_static_imports_include_tests_and_unused_code(self):
        policy = load_policy()
        from jsonschema import Draft202012Validator
        Draft202012Validator(json.loads((ROOT / "docs/schemas/player-dependencies.schema.json").read_text())).validate(policy)
        self.assertEqual(policy["external_packages"], ["numpy"])
        allowed = {"robot/__init__.py": "", "robot/helper.py": "from math import sin\n",
                   "robot/main.py": "from .helper import sin\nimport numpy as np\nfrom numpy.typing import NDArray\nfrom tankbot import Pose2D\nfrom tankbot.transforms import target_positions\n",
                   "tests/test_main.py": "import unittest\nimport numpy.testing\n"}
        validate_imports(allowed, policy)
        for source in ("import scipy", "from filterpy.kalman import KalmanFilter", "import sklearn", "import jsonschema", "import yaml", "import pip", "import subprocess", "import importlib", "import tankbot._imports", "from tankbot import _imports", "def unused():\n import scipy"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, r"robot/main.py:.*DEPENDENCY_NOT_ALLOWED"):
                validate_imports({**allowed, "robot/main.py": source}, policy)
        with self.assertRaises(ValueError): validate_imports({"main.py": "import unittest"}, policy)
        with self.assertRaises(ValueError): validate_imports({"tests/test_main.py": "import scipy"}, policy)

    def test_runtime_dynamic_import_rejects_even_preloaded_external_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "student.py").write_text('name = "filter" + "py"\nmodule = __import__(name)\n')
            script = '''import sys, types
from tankbot._imports import load_policy, install_workspace_imports, DependencyNotAllowed
sys.modules['filterpy'] = types.ModuleType('filterpy')
install_workspace_imports(sys.argv[1], load_policy())
sys.path.insert(0, sys.argv[1])
try:
    import student
except DependencyNotAllowed:
    print('blocked')
else:
    raise AssertionError('preloaded package bypassed runtime policy')
'''
            result = subprocess.run([sys.executable, "-c", script, directory], cwd=ROOT,
                                    env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "sdk/python")}, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "blocked")

    def test_matrix_shapes_readonly_backing_and_legacy_flat_constructor(self):
        for cls, args, size in ((Pose2D, (1, 2, .3), 3), (TargetEstimate, (1, 2), 2)):
            original = np.eye(size)
            value = cls(*args, covariance=original)
            self.assertEqual(value.covariance.shape, (size, size))
            self.assertEqual(value.covariance.dtype, np.float64)
            original[0, 0] = 99
            self.assertEqual(value.covariance[0, 0], 1)
            with self.assertRaises(ValueError): value.covariance[0, 0] = 3
            with self.assertRaises(ValueError): value.covariance.setflags(write=True)
            legacy = cls(*args, covariance=np.eye(size).ravel().tolist())
            np.testing.assert_array_equal(legacy.covariance, np.eye(size))
            with self.assertRaises(ValueError): cls(*args, covariance=np.zeros((size, size + 1)))
            for invalid in (np.eye(size,dtype=complex), np.full((size,size),"1"), np.full((size,size),object())):
                with self.assertRaises(TypeError): cls(*args, covariance=invalid)

    def test_sdk_flattens_matrices_only_at_unchanged_json_boundary(self):
        ctx = ModuleContext(6, .1, 12, {})
        for value, size in ((TargetEstimate(np.float32(1), np.int64(2), np.eye(2)), 2), (Pose2D(1, 2, .3, np.eye(3)), 3)):
            ctx.publish("out", value, frame_id="map")
            payload = ctx._outputs[-1][2]
            self.assertIs(type(payload["x_m"]),float if isinstance(value.x_m,np.floating) else int)
            self.assertEqual(payload["covariance"], np.eye(size).ravel().tolist())
            json.dumps(payload, allow_nan=False)
            restored = type(value)(**payload)
            np.testing.assert_array_equal(restored.covariance, value.covariance)

    def test_current_measurement_matrix_is_bounded_and_does_not_append_history(self):
        for index in range(10000):
            batch = () if index % 2 else (TargetEstimate(1, 2),)
            matrix = target_positions(batch)
            self.assertEqual(matrix.shape, (len(batch), 2))
            self.assertLessEqual(matrix.nbytes, 16)
        np.testing.assert_array_equal(target_positions((TargetEstimate(1, 2), TargetEstimate(3, 4))), np.array([[1, 2], [3, 4]]))

    def test_real_test_worker_rejects_dynamic_import_and_preserves_active_runtime(self):
        config = load_config(ROOT / "config/game.yaml")
        a = Authority(config, controlled=True)
        self.addCleanup(a.close)
        a.deployment = DeploymentManager(a)
        files = starter(config)
        files["localization/odometry.py"] = '''from tankbot import Module
class Odometry(Module):
    def update(self, inputs, ctx):
        forbidden = "filter" + "py"
        __import__(forbidden)
'''
        snapshot = {"files": files, "ledger": {}}
        snapshot["revision"] = digest(snapshot)
        worker = a.worker
        a.deployment.start("test", snapshot)
        deadline = time.monotonic() + 10
        while a.deployment.job and time.monotonic() < deadline:
            a.advance()
            if a.deployment.job and not a.deployment.job["worker"].ready: time.sleep(.002)
        self.assertIsNone(a.deployment.job)
        self.assertIn("DEPENDENCY_NOT_ALLOWED", a.deployment.last["error"])
        self.assertIs(a.worker, worker)
        files["localization/odometry.py"] = "import scipy\n"
        snapshot["revision"] = digest({"files": files, "ledger": {}})
        with self.assertRaisesRegex(ValueError, "DEPENDENCY_NOT_ALLOWED"): inspect_snapshot(snapshot, a)


if __name__ == "__main__": unittest.main()
