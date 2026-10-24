"""Settings persistence, progression authority and developer grant revocation."""
import copy
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python")]
from tankbot_host.application import ApplicationState, load_settings, validate_settings
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure
from tankbot_host.server import LocalServer
from tankbot_protocol.validation import Rejected


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = load_config(ROOT / "config/game.yaml")
        self.state = ApplicationState(self.config, self.directory / "settings.yaml", self.directory / "progress.json")

    def mode(self, enabled):
        value = self.state.public_settings()
        value["settings"]["developer_mode"] = enabled
        return self.state.update_settings({"revision": value["revision"], "settings": value["settings"]})

    def test_yaml_roundtrip_conflicts_and_malformed_input_never_overwrite(self):
        value = self.state.public_settings()
        value["settings"]["keyboard"]["forward"] = "ArrowUp"
        result = self.state.update_settings({"revision": value["revision"], "settings": value["settings"]})
        self.assertEqual(load_settings(self.state.settings_path)["keyboard"]["forward"], "ArrowUp")
        self.assertIn("forward: ArrowUp", self.state.settings_path.read_text())
        with self.assertRaisesRegex(ValueError, "其他窗口"):
            self.state.update_settings({"revision": value["revision"], "settings": value["settings"]})
        bad = copy.deepcopy(result["settings"]); bad["keyboard"]["fire"] = "ArrowUp"
        with self.assertRaisesRegex(ValueError, "同一个按键"):
            validate_settings(bad)
        bad = copy.deepcopy(result["settings"]); bad["keyboard"]["fire"] = "ControlLeft"
        with self.assertRaises(ValueError): validate_settings(bad)
        for raw in ("developer_mode: false\ndeveloper_mode: true\n", "!!python/object/apply:os.system ['false']", "version: true"):
            self.state.settings_path.write_text(raw)
            with self.assertRaises(ValueError): ApplicationState(self.config, self.state.settings_path, self.state.progress_path)
            self.assertEqual(self.state.settings_path.read_text(), raw)

    def test_ordered_progress_persists_retries_and_no_developer_awards(self):
        self.assertEqual(self.state.progress()["unlocked_levels"], ["c0"])
        with self.assertRaisesRegex(ValueError, "LEVEL_LOCKED"): self.state.require_level("c1")
        with self.assertRaisesRegex(ValueError, "REVOKED"): self.state.complete("invented", "c0")
        ticket = self.state.register_attempt("c0")
        self.state.complete(ticket, "c0")
        saved = self.state.progress_path.read_bytes()
        self.state.complete(ticket, "c0")
        self.assertEqual(self.state.progress_path.read_bytes(), saved)
        self.assertEqual(self.state.progress()["unlocked_levels"], ["c0", "c1"])
        self.state.select_level("c1")
        reopened = ApplicationState(self.config, self.state.settings_path, self.state.progress_path)
        self.assertEqual(reopened.progress()["current_level"], "c1")
        self.mode(True)
        practice = self.state.register_attempt("c2")
        self.state.select_level("c2")
        self.state.complete(practice, "c2")
        self.assertEqual(self.state.progress()["completed_levels"], ["c0"])
        self.assertEqual(self.state.progress()["current_level"], "c1")
        self.mode(False)
        with self.assertRaisesRegex(ValueError, "REVOKED"): self.state.complete(practice, "c2")
        with self.assertRaisesRegex(ValueError, "LEVEL_LOCKED"): self.state.require_level("c2")

    def test_corrupted_save_is_preserved_and_never_unlocks_by_unknown_record(self):
        for raw in ('{"version": 99}', json.dumps({"version": 1, "completed_levels": ["c2"], "current_level": "c2", "completions": {"c2": {"completed_at": "2026-10-24"}}})):
            self.state.progress_path.write_text(raw)
            with self.assertRaises(ValueError): self.state.progress()
            self.assertEqual(self.state.progress_path.read_text(), raw)

    def test_default_files_match_documented_schemas_and_cli_cannot_skip(self):
        from jsonschema import Draft202012Validator
        for filename, value in (("settings.schema.json", self.state.settings), ("progress.schema.json", self.state.read_progress())):
            Draft202012Validator(json.loads((ROOT / "docs/schemas" / filename).read_text())).validate(value)
        from tankbot_host.cli import main
        with mock.patch.object(sys, "argv", ["tankbot.py", "serve", "--level", "c2", "--settings-file", str(self.state.settings_path), "--save-file", str(self.state.progress_path)]), mock.patch("sys.stderr", new_callable=io.StringIO) as errors:
            with self.assertRaises(SystemExit) as result: main()
            self.assertEqual(result.exception.code, 2)
            self.assertIn("LEVEL_LOCKED", errors.getvalue())
        self.assertEqual(self.state.progress()["unlocked_levels"], ["c0"])

    def test_mode_does_not_grant_truth_to_python_or_player_view(self):
        config = configure(self.config, "c1")
        a = Authority(config, controlled=True)
        self.addCleanup(a.close)
        with self.assertRaisesRegex(Rejected, "UNAUTHORIZED"): a.developer_snapshot()
        a.developer_mode = True
        debug = a.developer_snapshot()
        self.assertIn("truth_pose", debug["truth"])
        self.assertEqual(a.view["payload"]["objects"], [])
        self.assertNotIn("truth_pose", json.dumps(a.worker_init))
        debug["truth"]["truth_pose"][0] = 10000
        self.assertNotEqual(a._private["truth_pose"][0], 10000)
        a.developer_mode = False
        with self.assertRaises(Rejected): a.developer_snapshot()

    def test_legacy_sandbox_requires_developer_and_cannot_switch_to_missing_campaign(self):
        config = copy.deepcopy(self.config); config.pop("campaign"); config["config_version"] = "1.5"
        state = ApplicationState(config, self.directory / "sandbox.yaml", self.directory / "sandbox.json")
        value = state.public_settings(); value["settings"]["developer_mode"] = True
        state.update_settings({"revision": value["revision"], "settings": value["settings"]})
        value = state.public_settings(); value["settings"]["developer_mode"] = False
        with self.assertRaisesRegex(ValueError, "没有教学关卡"):
            state.update_settings({"revision": value["revision"], "settings": value["settings"]})
        self.assertTrue(state.developer)
        self.assertEqual(state.progress()["unlocked_levels"], [])

    def test_http_enforces_unlocks_settings_csrf_and_mode_reset(self):
        config = configure(self.config, "c0"); config["host"]["port"] = 0
        a = Authority(config, controlled=True)
        server = LocalServer(a, workspace_store=self.directory / "workspace", application=self.state)
        thread = threading.Thread(target=server.http.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: server.authority.close())
        self.addCleanup(server.http.server_close); self.addCleanup(server.http.shutdown)
        def request(path, value=None, authenticated=True):
            conn = http.client.HTTPConnection("127.0.0.1", server.http.server_port, timeout=5)
            headers = {"Content-Type": "application/json"}
            if authenticated: headers.update(Origin=f"http://127.0.0.1:{server.http.server_port}", **{"X-TankBot-Control": server.token})
            conn.request("GET" if value is None else "POST", path, json.dumps(value) if value is not None else None, headers)
            response = conn.getresponse(); result = (response.status, json.loads(response.read())); conn.close(); return result
        self.assertEqual(request("/api/developer")[0], 403)
        self.assertEqual(request("/api/campaign/start", {"level_id": "c2"})[0], 400)
        a.finish_campaign(); server.save_progress()
        self.assertEqual(self.state.progress()["completed_levels"], [])
        value = self.state.public_settings(); value["settings"]["developer_mode"] = True
        body = {"revision": value["revision"], "settings": value["settings"]}
        self.assertEqual(request("/api/settings", body, False)[0], 403)
        self.assertEqual(request("/api/settings", body)[0], 200)
        self.assertEqual(request("/api/campaign/start", {"level_id": "c2"})[0], 200)
        self.assertIn("truth", request("/api/developer")[1])
        self.assertEqual(self.state.progress()["completed_levels"], [])
        value = self.state.public_settings(); value["settings"]["developer_mode"] = False
        self.assertEqual(request("/api/settings", {"revision": value["revision"], "settings": value["settings"]})[0], 200)
        self.assertEqual(server.authority.campaign.level_id, "c0")
        self.assertEqual(request("/api/developer")[0], 403)
        self.assertEqual(request("/api/campaign/start", {"level_id": "c1"})[0], 400)
        # A completion is trusted only after Authority marks its current attempt passed.
        server.authority._finish_campaign(passed=True); server.save_progress()
        self.assertEqual(request("/api/progress")[1]["completed_levels"], ["c0"])
        self.assertEqual(request("/api/campaign/start", {"level_id": "c1"})[0], 200)


if __name__ == "__main__": unittest.main()
