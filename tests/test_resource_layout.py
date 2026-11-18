"""Resource relocation preserves source bytes, trusted boundaries and the real entry."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ('host', 'protocol', 'sdk/python')]
from tankbot_host.authority import load_config, core_configuration
from tankbot_host.campaign import configure
from tankbot_host.configuration import load_yaml
from tankbot_host.level_templates import COMPONENTS, sources
from tankbot_host.resources import repository_path
from tankbot_host.template_resources import load_template_resource
from tankbot_host.workspace import starter


class ResourceLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / 'assets/config/game.yaml')
        cls.before = json.loads((ROOT / 'tests/fixtures/resource-layout-before.json').read_text())

    def test_all_chapters_generate_the_exact_previous_sources(self):
        def hashes(files):
            return {p: hashlib.sha256(s.encode()).hexdigest() for p, s in files.items()}
        self.assertEqual({k: hashes(v) for k, v in COMPONENTS.items()}, self.before['components'])
        for lid, definition in self.config['campaign']['levels'].items():
            with self.subTest(level=lid):
                self.assertEqual(hashes(sources(definition)), self.before['levels'][lid])
                files = starter(configure(self.config, lid))
                self.assertEqual(hashes({p: s for p, s in files.items() if p.endswith('.py')}), self.before['starter'][lid])

    def test_core_physics_inputs_and_protocol_identities_remain_unchanged(self):
        data = json.dumps(core_configuration(self.config), sort_keys=True, separators=(',', ':'))
        self.assertEqual(hashlib.sha256(data.encode()).hexdigest(), self.before['core_configuration_sha256'])
        for name in ('config', 'levels', 'templates', 'examples'):
            self.assertFalse((ROOT / name).exists())
            self.assertTrue((ROOT / 'assets' / name).is_dir())
        self.assertTrue((ROOT / 'protocol/tankbot_protocol/validation.py').is_file())
        self.assertFalse((ROOT / 'tools/tankbot.py').exists())
        self.assertFalse((ROOT / 'main.py').is_symlink())

    def test_old_config_references_resolve_only_to_new_assets(self):
        base = load_yaml(ROOT / 'assets/config/game.yaml')
        base['runtime']['profiles_file'] = 'config/runtime-profiles.yaml'
        base['level_plugins']['directory'] = 'levels'
        base['chassis_profiles'] = {key: value.removeprefix('assets/') for key, value in base['chassis_profiles'].items()}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.json'
            path.write_text(json.dumps(base))
            self.assertEqual(load_config(path), self.config)
        self.assertEqual(load_config(ROOT / 'config/game.yaml'), self.config)
        self.assertEqual(repository_path('config/../assets/config/game.yaml'), ROOT / 'assets/config/game.yaml')
        base['runtime']['profiles_file'] = 'assets/config/../../requirements.txt'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'escape.json'
            path.write_text(json.dumps(base))
            with self.assertRaisesRegex(ValueError, 'RUNTIME_PROFILE_PATH'):
                load_config(path)

    def test_template_sources_are_assets_not_embedded_programs(self):
        for name in ('campaign_templates', 'weapon_templates', 'weapon_curriculum', 'navigation_templates'):
            tree = ast.parse((ROOT / 'host/tankbot_host' / (name + '.py')).read_text())
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    self.assertFalse(isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and '\n' in node.value.value)
        for invalid in ('../main.py', 'weapons/../../main.py', '/etc/passwd', 'navigation/unknown.txt'):
            with self.subTest(resource=invalid), self.assertRaisesRegex(ValueError, 'INVALID_TEMPLATE_RESOURCE'):
                load_template_resource(invalid)

    def test_root_entry_bootstraps_without_site_packages_or_old_launcher(self):
        result = subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'main.py'), '--help'],
                                cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('main.py', result.stdout)
        self.assertNotIn('首次运行', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
