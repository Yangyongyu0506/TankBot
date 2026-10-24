"""Materialize a validated snapshot inside a fresh player runtime, never the Authority."""
import contextlib
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest
from tankbot._imports import install_workspace_imports, WorkspaceLoader


def prepare(init):
    temporary = None
    if "sources" in init:
        temporary = tempfile.TemporaryDirectory(prefix="tankbot-deployment-")
        for relative, source in init.pop("sources").items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*\.(py|json|md)", relative):
                raise ValueError("Unsafe source path")
            path = Path(temporary.name) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        init["workspace"] = temporary.name
    root = Path(init["workspace"])
    guard = install_workspace_imports(root, init["import_policy"])
    count = 0
    if init.pop("test_mode", False):
        root = Path(init["workspace"])
        sys.path.insert(0, str(root))
        with contextlib.redirect_stdout(sys.stderr):
            suite = unittest.TestSuite()
            for path in sorted(root.glob("tests/test_*.py")):
                import importlib.util
                spec = importlib.util.spec_from_file_location("player_test_" + path.stem, path)
                spec.loader = WorkspaceLoader(spec.name, path, guard)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            count = result.testsRun
            if not result.wasSuccessful():
                test, trace = (result.failures + result.errors)[0]
                location = "tests"
                for filename, line in re.findall(r'File "([^"]+)", line ([0-9]+)', trace):
                    if Path(filename).is_relative_to(root):
                        location = str(Path(filename).relative_to(root)) + ":" + line
                raise ValueError("PLAYER_TEST_FAILED " + location + ": " + trace.strip().splitlines()[-1][:160])
    return temporary, count
