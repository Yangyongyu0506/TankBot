"""Native-client lifecycle/configuration guards; real Godot flow is an explicit suite."""
from pathlib import Path
import copy
import contextlib
import hashlib
import io
import struct
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / path) for path in ('host', 'protocol', 'sdk/python')]
from tankbot_host.cli import parse_args
from tankbot_host.desktop import checked_binary, prepare_desktop, run_desktop, settings


class DesktopTests(unittest.TestCase):
    def test_schema_and_pinned_download(self):
        value = settings()
        self.assertEqual(value['desktop_version'], '1.0')
        self.assertEqual(len(value['engine']['linux_x86_64']['archive_sha512']), 128)

    def test_theme_readability_including_disabled_controls(self):
        appearance = settings()['client']['appearance']
        colors = appearance['colors']

        def luminance(key):
            rgb = [int(colors[key][i:i + 2], 16) / 255 for i in (1, 3, 5)]
            return sum((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) * w
                       for v, w in zip(rgb, (0.2126, 0.7152, 0.0722)))

        def contrast(first, second):
            low, high = sorted((luminance(first), luminance(second)))
            return (high + 0.05) / (low + 0.05)

        for prefix in ('button', 'start', 'stop'):
            for state in ('normal', 'hover', 'pressed', 'disabled'):
                fill = f'{prefix}_{state}' if state != 'disabled' else 'button_disabled'
                text = f'{prefix}_text' if state != 'disabled' else 'disabled_text'
                with self.subTest(control=prefix, state=state):
                    self.assertGreaterEqual(contrast(text, fill), appearance['readability']['minimum_text_contrast'])
                    self.assertGreaterEqual(contrast(fill, 'panel'), appearance['readability']['minimum_control_contrast'])
        for text in ('text', 'muted'):
            for surface in ('background', 'panel', 'inset'):
                with self.subTest(text=text, surface=surface):
                    self.assertGreaterEqual(contrast(text, surface), appearance['readability']['minimum_text_contrast'])

    def test_legacy_desktop_configuration_gets_the_same_validated_theme(self):
        from tankbot_host.configuration import load_yaml
        raw = load_yaml(ROOT / 'config/desktop.yaml')
        raw.pop('theme_file')
        raw.pop('sprites_file')
        appearance = load_yaml(ROOT / 'config/desktop-theme.yaml')
        sprites = load_yaml(ROOT / 'config/desktop-sprites.yaml')
        with patch('tankbot_host.configuration.load_yaml', side_effect=[raw, appearance, sprites]) as load:
            actual = settings()
        self.assertEqual(load.call_args_list[1].args[0], ROOT / 'config/desktop-theme.yaml')
        self.assertEqual(load.call_args_list[2].args[0], ROOT / 'config/desktop-sprites.yaml')
        self.assertEqual(actual['client']['appearance'], appearance)
        self.assertNotIn('appearance', actual['engine'])

    def test_invalid_theme_or_theme_path_is_rejected_before_launch(self):
        from jsonschema import ValidationError
        from tankbot_host.configuration import load_yaml
        raw = load_yaml(ROOT / 'config/desktop.yaml')
        appearance = load_yaml(ROOT / 'config/desktop-theme.yaml')
        appearance['colors']['button_normal'] = 'transparent'
        with patch('tankbot_host.configuration.load_yaml', side_effect=[raw, appearance]):
            with self.assertRaises(ValidationError):
                settings()
        raw['theme_file'] = '../other.yaml'
        with patch('tankbot_host.configuration.load_yaml', return_value=raw):
            with self.assertRaises(ValidationError):
                settings()

    def test_sprite_manifest_contains_real_bounded_rgba_art(self):
        sprites = settings()['client']['sprites']
        for name, definition in sprites['assets'].items():
            with self.subTest(asset=name):
                path = Path(definition['path'])
                self.assertTrue(path.is_relative_to(ROOT / 'assets/sprites'))
                if path.suffix == '.png':
                    header = path.read_bytes()[:33]
                    self.assertEqual(header[:8], b'\x89PNG\r\n\x1a\n')
                    width, height = struct.unpack('>II', header[16:24])
                    self.assertLessEqual(max(width, height), sprites['limits']['max_dimension_px'])
                    self.assertEqual(header[25], 6, 'sprite must carry an alpha channel')
                    x, y, w, h = definition['region_px']
                    self.assertLessEqual(x + w, width)
                    self.assertLessEqual(y + h, height)

    def test_missing_sprite_fails_before_launch(self):
        from tankbot_host.configuration import load_yaml
        raw = load_yaml(ROOT / 'config/desktop.yaml')
        appearance = load_yaml(ROOT / 'config/desktop-theme.yaml')
        sprites = load_yaml(ROOT / 'config/desktop-sprites.yaml')
        sprites['assets']['target']['path'] = 'assets/sprites/industrial/missing.png'
        with patch('tankbot_host.configuration.load_yaml', side_effect=[raw, appearance, sprites]):
            with self.assertRaisesRegex(ValueError, 'SPRITE_ASSET_MISSING: target'):
                settings()

    def test_cli_keeps_existing_modes_and_isolation_options(self):
        for mode in (None, 'headless', 'probe'):
            _, args = parse_args([*([mode] if mode else []), '--level', 'c1', '--workspace-store', '/tmp/isolated'])
            self.assertEqual(args.mode, mode or 'godot')
            self.assertEqual(args.workspace_store, Path('/tmp/isolated'))

    def test_retired_player_modes_fail_before_dependency_bootstrap(self):
        for mode in ('serve', 'browser', 'godot'):
            with self.subTest(mode=mode), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    parse_args([mode])
                self.assertEqual(result.exception.code, 2)

    def test_engine_version_rejected(self):
        with patch('tankbot_host.desktop.subprocess.run', return_value=Mock(stdout='3.6.stable')):
            with self.assertRaisesRegex(ValueError, 'Godot 4'):
                checked_binary('/tmp/not-a-godot-binary')

    def test_portable_download_is_verified_and_offline_cache_is_reused(self):
        spec = copy.deepcopy(settings())
        member = spec['engine']['linux_x86_64']['executable']
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as bundle:
            bundle.writestr(member, b'fixture executable')
            bundle.writestr('../must-not-be-extracted', b'ignored')
        archive = data.getvalue()
        spec['engine']['linux_x86_64']['archive_sha512'] = hashlib.sha512(archive).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target/debug').mkdir(parents=True)
            (root / 'target/debug/core_worker').touch()
            with patch('tankbot_host.desktop.ROOT', root), patch('tankbot_host.desktop.settings', return_value=spec), \
                    patch('tankbot_host.desktop.sys.platform', 'linux'), patch('tankbot_host.desktop.platform.machine', return_value='x86_64'), \
                    patch('tankbot_host.desktop.shutil.which', return_value=None), \
                    patch('tankbot_host.desktop.checked_binary', side_effect=lambda p: Path(p)), \
                    patch('tankbot_host.desktop.urlopen', return_value=io.BytesIO(archive)) as download:
                binary = prepare_desktop()
                self.assertEqual(binary.read_bytes(), b'fixture executable')
                self.assertEqual(prepare_desktop(offline=True), binary)
                download.assert_called_once()
                self.assertEqual([p.name for p in binary.parent.iterdir()], [member])

    def test_bad_download_checksum_never_installs(self):
        spec = settings()
        with tempfile.TemporaryDirectory() as directory, patch('tankbot_host.desktop.ROOT', Path(directory)), \
                patch('tankbot_host.desktop.settings', return_value=spec), \
                patch('tankbot_host.desktop.sys.platform', 'linux'), patch('tankbot_host.desktop.platform.machine', return_value='x86_64'), \
                patch('tankbot_host.desktop.shutil.which', return_value=None), \
                patch('tankbot_host.desktop.urlopen', return_value=io.BytesIO(b'bad download')):
            with self.assertRaisesRegex(ValueError, 'SHA-512'):
                prepare_desktop()
            self.assertFalse(any(p.is_file() for p in Path(directory).rglob('*')))

    def test_offline_without_engine_never_downloads(self):
        spec = settings()
        with tempfile.TemporaryDirectory() as directory, patch('tankbot_host.desktop.ROOT', Path(directory)), \
                patch('tankbot_host.desktop.settings', return_value=spec), \
                patch('tankbot_host.desktop.sys.platform', 'linux'), patch('tankbot_host.desktop.platform.machine', return_value='x86_64'), \
                patch('tankbot_host.desktop.shutil.which', return_value=None), patch('tankbot_host.desktop.urlopen') as download:
            with self.assertRaisesRegex(ValueError, '离线'):
                prepare_desktop(offline=True)
            download.assert_not_called()

    def test_window_exit_stops_service_and_current_authority(self):
        stop = threading.Event()
        server = Mock()
        server.http.server_address = ('127.0.0.1', 12345)
        server.serve.side_effect = lambda: stop.wait(5)
        server.http.shutdown.side_effect = stop.set
        process = Mock()
        process.wait.return_value = 0
        process.poll.return_value = 0
        with patch('tankbot_host.desktop.subprocess.Popen', return_value=process) as launch:
            run_desktop(server, Path('/tmp/godot'))
        self.assertIn('--backend-url=http://127.0.0.1:12345', launch.call_args.args[0])
        self.assertFalse(any('token' in arg for arg in launch.call_args.args[0]))
        server.http.shutdown.assert_called_once()
        server.authority.close.assert_called_once()

    def test_failed_client_launch_still_cleans_up(self):
        stop = threading.Event()
        server = Mock()
        server.http.server_address = ('127.0.0.1', 12345)
        server.serve.side_effect = lambda: stop.wait(5)
        server.http.shutdown.side_effect = stop.set
        with patch('tankbot_host.desktop.subprocess.Popen', side_effect=OSError('missing binary')):
            with self.assertRaises(OSError):
                run_desktop(server, Path('/tmp/godot'))
        server.http.shutdown.assert_called_once()
        server.authority.close.assert_called_once()
