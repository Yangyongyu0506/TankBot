"""Discovery must include new components and propagate failures to local/CI callers."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FrontendEntryTests(unittest.TestCase):
    def run_entry(self,*args):
        return subprocess.run(['node',str(ROOT/'tools/test_frontend.mjs'),*args],cwd=ROOT,capture_output=True,text=True)

    def test_existing_component_tests_are_discovered_without_a_registration_list(self):
        result=self.run_entry('--list');self.assertEqual(result.returncode,0,result.stderr)
        paths={Path(p).name for p in json.loads(result.stdout)}
        expected={p.name for p in (ROOT/'tests').glob('test_*.mjs') if p.name!='test_wasm.mjs'}
        self.assertEqual(paths,expected)
        wasm=self.run_entry('--wasm','--list')
        self.assertEqual([Path(p).name for p in json.loads(wasm.stdout)],['test_wasm.mjs'])

    def test_new_nested_tests_and_failures_are_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'component';path.mkdir()
            (path/'test_new_component.mjs').write_text('import test from "node:test";\ntest("discovered callback",()=>{throw new Error("intentional discovery failure");});\n')
            (path/'helper.mjs').write_text('throw new Error("must not run a helper");\n')
            result=self.run_entry('--directory',directory)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('intentional discovery failure',result.stdout+result.stderr)
            self.assertNotIn('must not run a helper',result.stdout+result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            self.assertNotEqual(self.run_entry('--directory',directory).returncode,0)
