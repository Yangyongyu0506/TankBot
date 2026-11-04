"""Inspect the real prerequisite graph without creating a world or changing player files."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python")]
from tankbot_host.authority import load_config
from tankbot_host.cli import main, parse_args
from tankbot_host.progression import LevelProgression, format_level_tree


class LevelTreeCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config/game.yaml")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.save = self.directory / "profile/progress.json"
        self.settings = self.directory / "profile/settings.yaml"
        self.workspace = self.directory / "workspaces"

    def invoke(self, *extra):
        args = ["tankbot.py", "--level-tree", "--save-file", str(self.save),
                "--settings-file", str(self.settings), "--workspace-store", str(self.workspace), *extra]
        output = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output), \
                patch("tankbot_host.authority.Authority", side_effect=AssertionError("must not start physics")), \
                patch("tankbot_host.application.ApplicationState", side_effect=AssertionError("must not initialize profile")):
            main()
        return output.getvalue()

    def saved(self, done, current):
        value = {"version": 1, "completed_levels": done, "current_level": current,
                 "completions": {lid: {"completed_at": "2026-11-04T00:00:00+00:00"} for lid in done}}
        self.save.parent.mkdir(parents=True, exist_ok=True)
        self.save.write_text(json.dumps(value, ensure_ascii=False))
        return value

    def line(self, output, lid):
        return next(line for line in output.splitlines() if line.lstrip("│ ├└─").startswith(lid + "  "))

    def test_standalone_parser_help_and_inspection_flags(self):
        self.assertTrue(parse_args(["--level-tree"])[1].level_tree)
        self.assertTrue(parse_args(["--list-maps"])[1].list_maps)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--level-tree", "--list-maps"])

    def test_new_player_tree_never_creates_profile_or_workspace(self):
        output = self.invoke()
        self.assertIn(f"已通关 0 / {len(self.config['campaign']['levels'])}", output)
        self.assertIn("可挑战；当前关卡", self.line(output, "c0"))
        for lid in ("c1", "navigation.c0"):
            self.assertIn("未解锁；缺少：c0", self.line(output, lid))
        self.assertIn("├── c1", output)
        self.assertIn("└── navigation.c0", output)
        self.assertIn("未创建文件", output)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_root_completion_opens_both_branches_without_writing_files(self):
        self.saved(["c0"], "navigation.c0")
        raw, mtime = self.save.read_bytes(), self.save.stat().st_mtime_ns
        output = self.invoke("--developer")
        self.assertIn("已通关", self.line(output, "c0"))
        for lid in ("c1", "navigation.c0"):
            self.assertIn("可挑战", self.line(output, lid))
        self.assertIn("当前关卡", self.line(output, "navigation.c0"))
        self.assertIn("未解锁；缺少：c1", self.line(output, "c2"))
        self.assertEqual(self.save.read_bytes(), raw)
        self.assertEqual(self.save.stat().st_mtime_ns, mtime)
        self.assertEqual(list(self.save.parent.iterdir()), [self.save])
        self.assertFalse(self.workspace.exists())

    def test_nonprefix_navigation_and_old_chain_saves_have_same_unlocks_as_launcher(self):
        progression = LevelProgression(self.config)
        for done, current in ((["c0", "navigation.c0", "navigation.c1"], "navigation.c2"),
                              (["c0", "c1", "c2", "c3", "c4", "c5"], "c5")):
            with self.subTest(done=done):
                value = self.saved(done, current)
                raw = self.save.read_bytes()
                output = self.invoke()
                unlocked = progression.unlocked_levels(value["completed_levels"])
                for lid in progression.levels:
                    state = "已通关" if lid in done else "可挑战" if lid in unlocked else "未解锁"
                    self.assertIn(state, self.line(output, lid))
                self.assertEqual(self.save.read_bytes(), raw)

    def test_invalid_saves_fail_clearly_and_remain_unchanged(self):
        for raw in ('{"version":99}', '{"version":1,"version":1}',
                    '{"version":1,"completed_levels":[],"current_level":"c2","completions":{}}',
                    'x' * 65537):
            with self.subTest(raw=raw[:80]):
                self.save.parent.mkdir(parents=True, exist_ok=True)
                self.save.write_text(raw)
                with contextlib.redirect_stderr(io.StringIO()) as errors, self.assertRaises(SystemExit) as raised:
                    self.invoke()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("error:", errors.getvalue())
                self.assertEqual(self.save.read_text(), raw)
                self.assertEqual(list(self.save.parent.iterdir()), [self.save])

    def test_custom_ids_display_order_and_all_prerequisite_edges_are_not_hardcoded(self):
        entries = [("join", ["left", "right"]), ("right", ["root"]), ("root", []),
                   ("left", ["root"]), ("finish", ["join"])]
        config = {"campaign": {"levels": {
            lid: {"title": "Task " + lid, "metadata": {"prerequisites": parents}} for lid, parents in entries
        }}}
        progression = LevelProgression(config)
        value = progression.new_progress()
        value["completed_levels"] = ["right", "root"]
        output = format_level_tree(progression, value)
        self.assertEqual(output.count("join  Task join"), 2)
        self.assertEqual(output.count("finish  Task finish"), 1)
        self.assertIn("需全部通关：left、right", output)
        self.assertIn("缺少：left", self.line(output, "join"))
        self.assertIn("同一节点，已在上方展开", output)
        self.assertEqual(progression.initial_level, "root")

    def test_custom_config_is_used_and_empty_sandbox_catalogue_is_explained(self):
        config = copy.deepcopy(self.config)
        config.pop("campaign")
        with patch("tankbot_host.authority.load_config", return_value=config) as loader:
            output = self.invoke("--config", str(self.directory / "sandbox.yaml"))
        loader.assert_called_once_with(self.directory / "sandbox.yaml")
        self.assertIn("此配置没有教学关卡", output)
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
