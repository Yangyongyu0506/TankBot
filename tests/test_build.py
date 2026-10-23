"""Regression checks for the unified Rust/editor build entry point."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("tankbot_build", Path(__file__).resolve().parents[1] / "tools/build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        manifest = {"dependencies": {"editor": "1.0.0"}, "devDependencies": {"esbuild": "0.28.2"}}
        lock = {"packages": {
            "": manifest,
            "node_modules/editor": {"version": "1.0.0"},
            "node_modules/esbuild": {"version": "0.28.2"},
            "node_modules/@esbuild/linux-x64": {"version": "0.28.2", "optional": True, "os": ["linux"], "cpu": ["x64"]},
            "node_modules/@esbuild/win32-x64": {"version": "0.28.2", "optional": True, "os": ["win32"], "cpu": ["x64"]},
        }}
        (self.root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        self.platform = {"platform": "linux", "arch": "x64"}

    def install(self, relative, version):
        path = self.root / relative / "package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": version}), encoding="utf-8")
        if relative.startswith("node_modules/@esbuild/"):
            binary = path.parent / "bin/esbuild"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("binary", encoding="utf-8")

    def test_checks_all_required_packages_and_native_binary(self):
        self.assertFalse(build.dependencies_ready(self.root, self.platform))
        self.install("node_modules/editor", "1.0.0")
        self.install("node_modules/esbuild", "0.28.2")
        self.assertFalse(build.dependencies_ready(self.root, self.platform))
        self.install("node_modules/@esbuild/linux-x64", "0.28.2")
        self.assertTrue(build.dependencies_ready(self.root, self.platform))
        self.install("node_modules/editor", "0.9.0")
        self.assertFalse(build.dependencies_ready(self.root, self.platform))
        self.install("node_modules/editor", "1.0.0")
        self.assertFalse(build.dependencies_ready(self.root, {"platform": "win32", "arch": "x64"}))
        (self.root / "node_modules/@esbuild/linux-x64/bin/esbuild").unlink()
        self.assertFalse(build.dependencies_ready(self.root, self.platform))
        self.install("node_modules/@esbuild/linux-x64", "0.28.2")
        (self.root / "node_modules/editor/package.json").write_text("{", encoding="utf-8")
        self.assertFalse(build.dependencies_ready(self.root, self.platform))

    def test_drifted_manifest_is_not_silently_accepted(self):
        (self.root / "package.json").write_text(json.dumps({"dependencies": {"editor": "2.0.0"}}), encoding="utf-8")
        with self.assertRaisesRegex(build.BuildError, "package-lock.json"):
            build.dependencies_ready(self.root, self.platform)

    def test_web_build_installs_then_reuses_and_rebuilds(self):
        commands = []

        def fake_run(command, root, env):
            commands.append(command)
            if command[1] == "ci":
                for name in ("editor", "esbuild", "@esbuild/linux-x64"):
                    self.install("node_modules/" + name, "1.0.0" if name == "editor" else "0.28.2")
            else:
                for name in ("editor-bundle.js", "THIRD_PARTY_NOTICES.txt"):
                    path = root / "build/web" / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("built", encoding="utf-8")

        with mock.patch.object(build, "node_tools", return_value=("npm", self.platform)), mock.patch.object(build, "run", side_effect=fake_run):
            build.build_editor(self.root, {}, offline=True)
            build.build_editor(self.root, {}, offline=True)
        self.assertEqual([cmd[1] for cmd in commands], ["ci", "run", "run"])
        self.assertIn("--offline", commands[0])
        self.assertIn("--include=dev", commands[0])
        self.assertIn("--include=optional", commands[0])

    def test_missing_bundle_is_a_failure(self):
        for name in ("editor", "esbuild", "@esbuild/linux-x64"):
            self.install("node_modules/" + name, "1.0.0" if name == "editor" else "0.28.2")
        with mock.patch.object(build, "node_tools", return_value=("npm", self.platform)), mock.patch.object(build, "run"):
            with self.assertRaisesRegex(build.BuildError, "editor-bundle.js"):
                build.build_editor(self.root, {}, offline=False)

    def test_format_check_does_not_require_node(self):
        with mock.patch.object(build, "node_tools", side_effect=AssertionError("Node should not be checked")), mock.patch.object(build, "build_core") as core, mock.patch.object(build, "build_editor") as editor:
            self.assertEqual(build.main(["--format-check"]), 0)
            core.assert_called_once()
            editor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
