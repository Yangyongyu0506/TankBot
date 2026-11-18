"""Native-client lifecycle/configuration guards; real Godot flow is an explicit suite."""
from pathlib import Path
import copy
import hashlib
import io
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

    def test_cli_keeps_existing_modes_and_isolation_options(self):
        for mode in ('serve', 'browser', 'godot', 'headless', 'probe'):
            _, args = parse_args([mode, '--level', 'c1', '--workspace-store', '/tmp/isolated'])
            self.assertEqual(args.mode, mode)
            self.assertEqual(args.workspace_store, Path('/tmp/isolated'))

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
