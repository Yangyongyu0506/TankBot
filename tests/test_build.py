"""Core builds never install or invoke removed browser/editor dependencies."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('tankbot_build', Path(__file__).resolve().parents[1] / 'tools/build.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class BuildTests(unittest.TestCase):
    def test_default_build_only_builds_core(self):
        with mock.patch.object(build, 'build_core') as core:
            self.assertEqual(build.main([]), 0)
            self.assertFalse(core.call_args.args[2].wasm)
            self.assertFalse(core.call_args.args[2].format_check)

    def test_wasm_and_format_modes_are_retained(self):
        for option, attribute in (('--wasm', 'wasm'), ('--format-check', 'format_check')):
            with self.subTest(option=option), mock.patch.object(build, 'build_core') as core:
                self.assertEqual(build.main([option, '--offline']), 0)
                self.assertTrue(getattr(core.call_args.args[2], attribute))
                self.assertTrue(core.call_args.args[2].offline)

    def test_build_error_returns_nonzero(self):
        with mock.patch.object(build, 'build_core', side_effect=build.BuildError('fixture failure')):
            self.assertEqual(build.main([]), 1)

    def test_core_build_command_has_no_node_dependency(self):
        root = Path('/tmp/core-build-fixture')
        args = mock.Mock(format_check=False, release=False, offline=True, wasm=False)
        with mock.patch.object(build, 'cargo_tool', return_value='cargo'), mock.patch.object(build, 'run') as run:
            build.build_core(root, {}, args)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[-1], ['cargo', 'build', '--locked', '--offline'])
        self.assertFalse(any('npm' in command or 'node' in command for command in commands))
