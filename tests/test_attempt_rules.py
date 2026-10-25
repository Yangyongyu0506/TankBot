"""Authority deadlines, deployed-code start, manual abort and actual lethal self-hits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/name) for name in ("host", "protocol", "sdk/python")]
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure, CampaignSession
from tankbot_host.configuration import load_yaml
from tankbot_host.deployment import DeploymentManager
from tankbot_host.workspace import WorkspaceStore
from tankbot_protocol.validation import Rejected
from campaign_support import solutions

ZERO = {"linear": {"x": 0, "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}


class AttemptRulesTests(unittest.TestCase):
    def config(self, level, seconds=1):
        config = configure(load_config(ROOT/"config/game.yaml"), level)
        config["campaign"]["levels"][level]["time_limit_s"] = seconds
        return config

    def authority(self, config, **kwargs):
        a = Authority(config, controlled=True, **kwargs)
        self.addCleanup(a.close)
        return a

    def finish_job(self, a):
        until = time.monotonic()+15
        while a.deployment.job and time.monotonic() < until:
            a.advance()
            time.sleep(.001)
        self.assertIsNone(a.deployment.job, a.deployment.status())
        return a.deployment.last

    def test_yaml_is_canonical_and_ambiguous_configuration_is_rejected(self):
        config = load_config(ROOT/"config/game.yaml")
        self.assertEqual(config, json.loads((ROOT/"core/tests/fixtures/default-profile.json").read_text()))
        self.assertEqual([d["time_limit_s"] for d in config["campaign"]["levels"].values()], [60,60,120,120,180])
        self.assertEqual(config["campaign"]["lessons"]["c1"]["functions"][0]["name"], "radar_to_map")
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"invalid.yaml"
            for source in ("a: 1\na: 2\n", "a: !!python/object:object {}", "a: .nan\n", "a: &loop [*loop]\n", "a: 2026-10-25\n"):
                p.write_text(source)
                with self.subTest(source=source), self.assertRaises(ValueError):
                    load_yaml(p)

    def test_manual_first_effective_control_starts_and_exact_tick_times_out(self):
        a = self.authority(self.config("c0"))
        for _ in range(120): a.advance()
        a.keyboard(copy.deepcopy(ZERO)); a.turret_keyboard({"velocity_radps":0})
        self.assertIsNone(a.campaign.started_tick)
        move = copy.deepcopy(ZERO); move["linear"]["x"] = .1
        a.keyboard(move)
        start = a.tick
        self.assertEqual(a.campaign.started_tick, start)
        for _ in range(a.hz-1): a.advance()
        self.assertEqual(a.campaign.status, "active")
        a.advance()
        self.assertEqual(a.campaign.result["reason"], "timeout")
        self.assertEqual(a.campaign.result["finished_tick"], start+a.hz)
        report = a.campaign_status()
        for _ in range(12): a.advance()
        self.assertEqual(a.campaign_status(), report)

    def test_test_does_not_start_timer_first_deployment_starts_and_redeploy_preserves_it(self):
        config = self.config("c1", seconds=20)
        a = self.authority(config)
        a.deployment = DeploymentManager(a)
        with tempfile.TemporaryDirectory() as directory:
            snapshot = WorkspaceStore(directory, solutions(config), config["workspace"]).read()
            for _ in range(a.hz*2): a.advance()
            with self.assertRaisesRegex(Rejected, "DEPLOY_TO_START_ATTEMPT"):
                a.fire_keyboard({"request_id":"before-deploy"})
            a.deployment.start("test", snapshot)
            self.assertEqual(self.finish_job(a)["status"], "Ready")
            self.assertIsNone(a.campaign.started_tick)
            self.assertEqual(a.campaign.public()["timing"]["remaining_s"],20)
            a.deployment.start("deploy", snapshot)
            self.assertEqual(self.finish_job(a)["status"], "Active")
            start = a.campaign.started_tick
            self.assertEqual(start, a.deployment.active["activated_tick"])
            for _ in range(30): a.advance()
            a.deployment.start("deploy", snapshot)
            self.assertEqual(self.finish_job(a)["status"], "Active")
            self.assertEqual(a.campaign.started_tick, start)
            self.assertLess(a.campaign.public()["timing"]["remaining_s"],20)
            a.finish_campaign()
            self.assertEqual(a.campaign.result["reason"],"aborted")
            self.assertIsNone(a._pending)
            self.assertIsNone(a.deployment.job)
            with self.assertRaisesRegex(ValueError,"ATTEMPT_ENDED"):a.deployment.start("test",snapshot)

    def test_lethal_reflected_shots_fail_level_and_remove_player_from_view(self):
        config = self.config("c2", seconds=120)
        self.assertEqual(config["scene"]["player_health"],config["weapons"]["targets"][0]["health"])
        config["scene"]["walls"] = [{"center":[1.5,0],"size":[.05,4]}]
        a = self.authority(config, startup_sources=solutions(config))
        observed = {a.campaign.player_hp}
        for _ in range(240):
            # Wait for the returning shot; firing too early destroys both projectiles in flight.
            if a.tick % 60 == 0:a.fire_keyboard({"request_id":f"return-{a.tick}"})
            a.advance();observed.add(a.campaign.player_hp)
            if a.campaign.status != "active":break
        self.assertEqual(observed,{3,2,1,0})
        self.assertEqual(a.campaign.result["reason"],"player_dead")
        self.assertFalse(a._private["player_alive"])
        self.assertIsNone(a._private["turret_state"])
        self.assertIsNone(a.view["payload"]["selected_pose"])
        self.assertEqual(a.view["payload"]["local_observations"],[])
        with self.assertRaisesRegex(Rejected,"ATTEMPT_ENDED"):a.keyboard(ZERO)
        result=a.campaign_status()
        for _ in range(60):a.advance()
        self.assertEqual(a.campaign_status(),result)

    def test_terminal_priority_inclusive_deadline_and_late_kill(self):
        config = self.config("c2")
        a = self.authority(config, startup_sources=solutions(config))
        private = copy.deepcopy(a._private)
        private["targets"][0].update(alive=False,hp=0)
        for alive,tick,expected in ((True,59,"objective_completed"),(True,60,"objective_completed"),(True,61,"timeout"),(False,60,"player_dead")):
            session=CampaignSession(config);session.start(0)
            private["player_alive"]=alive;private["player_hp"]=3 if alive else 0
            self.assertEqual(session.outcome(private,tick),expected)
        # An explicit abort freezes the report and never awards a later kill.
        a.finish_campaign();a._private=private
        self.assertEqual(a.campaign_status()["attempt"]["result"]["reason"],"aborted")


if __name__ == "__main__": unittest.main()
