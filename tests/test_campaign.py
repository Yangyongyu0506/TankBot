"""M4 sensor, capability, lifecycle and playable-loop acceptance checks."""
import copy
from dataclasses import FrozenInstanceError
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python")]
from tankbot import RadarData, TargetEstimate
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure, RadarSimulator
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_protocol.message import envelope
from tankbot_protocol.validation import Validator, Rejected
from campaign_support import solutions, EMA, WINDOW, AimHarness


class CampaignTests(unittest.TestCase):
    def config(self, level):
        return configure(load_config(ROOT / "config/m1.json"), level)

    def authority(self, level, tracker=EMA):
        config = self.config(level)
        authority = Authority(config, controlled=True, startup_sources=solutions(config, tracker))
        self.addCleanup(authority.close)
        return authority

    def test_radar_visibility_seed_noise_dropout_and_dead_target(self):
        config = self.config("c2")
        config["scene"]["walls"] = []
        private = {"truth_pose": [0, 0, 0], "targets": [{"target_id": "secret_entity_id", "pose": [4, 0, 0], "alive": True}]}
        radar = RadarSimulator(config)
        measurements = [radar.sample(private, tick*6)["detections"] for tick in range(1000)]
        missing = sum(not detections for detections in measurements)
        ranges = [row[0]["range_m"]-4 for row in measurements if row]
        bearings = [row[0]["bearing_rad"] for row in measurements if row]
        self.assertLess(abs(missing-100), 40)
        self.assertAlmostEqual(statistics.pstdev(ranges), .15, delta=.02)
        self.assertAlmostEqual(statistics.pstdev(bearings), .02, delta=.003)
        other = RadarSimulator(config)
        self.assertEqual(measurements[:20], [other.sample(private, tick*6)["detections"] for tick in range(20)])
        self.assertNotIn("secret_entity_id", json.dumps(measurements))
        private["targets"][0]["alive"] = False
        self.assertEqual(radar.sample(private, 6000)["detections"], [])
        config = self.config("c1")
        radar = RadarSimulator(config)
        private["targets"][0].update(pose=[3, 0, 0], alive=True)
        self.assertEqual(radar.sample(private, 0)["detections"], [])  # center wall occludes
        config["scene"]["walls"] = []
        config["campaign"]["radar"]["field_of_view_rad"] = math.pi
        private["targets"][0]["pose"] = [-3, 0, 0]
        self.assertEqual(radar.sample(private, 6)["detections"], [])
        private["targets"][0]["pose"] = [13, 0, 0]
        self.assertEqual(radar.sample(private, 12)["detections"], [])
        private["targets"][0]["pose"] = [3, 0, 0]
        self.assertEqual(radar.sample(private, 18)["detections"][0]["range_m"], 3)
        self.assertIsNone(radar.sample(private, 18))
        self.assertIsNone(radar.sample(private, 19))

    def test_sdk_values_and_target_schema_covariance_time_and_permissions(self):
        radar = RadarData([{"observation_id": "one", "range_m": 1.0, "bearing_rad": 0.0}])
        self.assertIsInstance(radar.detections, tuple)
        with self.assertRaises(FrozenInstanceError):
            radar.detections[0].range_m = 5
        point = TargetEstimate(1, 2, [1, 0, 0, 1])
        self.assertIsInstance(point.covariance, tuple)
        config = self.config("c2")
        channel = "/robot/estimates/perception/target"
        msg = envelope("target_estimate@1", channel, {"x_m": 1, "y_m": 2, "covariance": [1, 0, 0, 1]},
                       tick=6, hz=60, run_id="test", publisher_id="module:perception", sequence=1, frame_id="map")
        grant = {("module:perception", channel, "target_estimate@1", "map")}
        Validator(config, "test").validate(msg, now=12, grants=grant, source_tick=6)
        for covariance in ([1, 2, 2, 1], [-1, 0, 0, 1], [1, .1, 0, 1]):
            bad = copy.deepcopy(msg)
            bad["payload"]["covariance"] = covariance
            with self.assertRaisesRegex(Rejected, "INVALID_COVARIANCE"):
                Validator(config, "test").validate(bad, now=12, grants=grant)
        with self.assertRaisesRegex(Rejected, "STALE_DATA"):
            Validator(config, "test").validate(msg, now=100, grants=grant)
        with self.assertRaisesRegex(Rejected, "UNAUTHORIZED"):
            Validator(config, "test").validate(msg, now=12, grants=set())

    def test_new_templates_append_without_overwriting_prior_algorithm(self):
        with tempfile.TemporaryDirectory() as directory:
            api = WorkspaceAPI(self.config("c0"), directory=directory)
            original = api.get()["snapshot"]
            self.assertNotIn("perception/transforms.py", original["files"])
            api.unlock(self.config("c1"))
            snapshot = api.get()["snapshot"]
            api.post("save", {"revision": snapshot["revision"], "changes": {"perception/transforms.py": "MY_ALGORITHM = True\n"}})
            api.unlock(self.config("c2"))
            snapshot = api.get()["snapshot"]
            self.assertEqual(snapshot["files"]["perception/transforms.py"], "MY_ALGORITHM = True\n")
            self.assertIn("perception/tracker.py", snapshot["files"])
            self.assertEqual(set(snapshot["ledger"]), {"campaign-c0-unlock", "campaign-c1-unlock", "campaign-c2-unlock"})
            revision = snapshot["revision"]
            api.unlock(self.config("c1"))
            self.assertEqual(api.get()["snapshot"]["revision"], revision)
            self.assertEqual(snapshot["files"]["tankbot.json"], original["files"]["tankbot.json"])

    def test_wrong_estimate_stays_wrong_and_old_samples_cannot_replace_newer_state(self):
        config = self.config("c1")
        sources = solutions(config)
        sources["campaign_robot.py"] = '''from tankbot import Module, TargetEstimate
class CampaignRobot(Module):
    def update(self, inputs, ctx):
        recent = ctx.simulation_tick <= 12
        ctx.publish("target", TargetEstimate(7 if recent else 99, 8), frame_id="map",
                    simulation_tick=ctx.simulation_tick if recent else 6)
'''
        a = Authority(config, controlled=True, startup_sources=sources)
        self.addCleanup(a.close)
        for _ in range(36):
            a.advance()
        self.assertEqual(a._target_estimate["simulation_tick"], 12)
        self.assertEqual(a.view["payload"]["target_estimates"][0]["payload"]["x_m"], 7)
        self.assertEqual(a._private["targets"][0]["pose"], config["weapons"]["targets"][0]["pose"])
        self.assertEqual(a._private["truth_pose"], config["scene"]["initial_pose"])

    def test_c0_manual_controls_and_truth_practice_are_playable(self):
        a = self.authority("c0")
        for _ in range(1800):
            if a.tick % a.period == 0:
                p = a._sensors["/robot/localization/pose"]["payload"]
                objective = a.campaign.public()["progress"]
                a.keyboard({"linear": {"x": 1.0 if not objective["moved"] else 0.0, "y": 0.0, "z": 0.0},
                            "angular": {"x": 0.0, "y": 0.0, "z": 1.0 if objective["moved"] and not objective["turned"] else 0.0}})
                target = next(obj for obj in a.view["payload"]["objects"] if obj["kind"] == "target")
                turret = a._sensors["/robot/turret/joint_states"]["payload"]["position"][0]
                desired = math.atan2(target["pose"]["y_m"]-p["y_m"], target["pose"]["x_m"]-p["x_m"])
                error = (desired-p["yaw_rad"]-turret+math.pi)%math.tau-math.pi
                a.turret_keyboard({"velocity_radps": max(-2.0, min(2.0, 4*error))})
                if abs(error) < .03 and a._sensors["/robot/weapons/cannon/state"]["payload"]["ready"]:
                    a.fire_keyboard({"request_id": f"practice-{a.tick}"})
            a.advance()
            if a.campaign.status == "passed":
                break
        self.assertEqual(a.campaign.status, "passed", a.campaign_status())
        self.assertEqual(a.view["payload"]["selected_pose"]["source_id"], "system")
        self.assertNotIn("/robot/sensors/radar", a._sensors)

    def test_c1_function_estimate_and_hit_complete_the_problem(self):
        a = self.authority("c1")
        aim = AimHarness()
        for _ in range(1800):
            if a.tick % a.period == 0:
                aim.step(a)
            a.advance()
            self.assertEqual(a.view["payload"]["objects"], [])
            self.assertEqual(a.view["payload"]["effects"], [])
            if a.campaign.status == "passed":
                break
        self.assertEqual(a.campaign.status, "passed", a.campaign_status())
        self.assertLess(a.campaign.result["rmse_m"], 1e-10)

    def test_c2_two_tracking_methods_kill_using_estimates_and_authorized_controls(self):
        for tracker in (EMA, WINDOW):
            with self.subTest(method="ema" if tracker == EMA else "window"):
                a = self.authority("c2", tracker)
                aim = AimHarness()
                positions = []
                for _ in range(7200):
                    if a.tick % a.period == 0:
                        aim.step(a)
                    a.advance()
                    positions.append(a._private["targets"][0]["pose"][:2])
                    self.assertEqual(a.view["payload"]["objects"], [])
                    if a.campaign.status == "passed":
                        break
                    self.assertIsNone(a.campaign_status()["attempt"]["result"])
                self.assertEqual(a.campaign.status, "passed", a.campaign_status())
                self.assertEqual(a.campaign.hp, 0)
                self.assertFalse(a._private["targets"][0]["alive"])
                self.assertGreater(math.dist(positions[0], positions[min(180, len(positions)-1)]), .5)
                self.assertTrue(math.isfinite(a.campaign.result["rmse_m"]))
                old_tick = a.tick
                for _ in range(12):
                    a.advance()
                self.assertEqual(a.tick, old_tick+12)  # remaining projectiles/physics still advance
                with self.assertRaisesRegex(Rejected, "ATTEMPT_ENDED"):
                    a.fire_keyboard({"request_id": "after-end"})

    def test_hidden_truth_never_enters_profile_runtime_or_view_and_scoring_is_terminal(self):
        a = self.authority("c2")
        for _ in range(60):
            a.advance()
        profile = json.dumps(a.public_profile())
        self.assertNotIn("waypoints_m", profile)
        self.assertNotIn("initial_velocity", profile)
        self.assertEqual(set(a.worker_init["config"]), {"initial_pose", "wheels", "module", "lesson"})
        self.assertEqual(set(a.input_channels.values()), {"/robot/localization/pose", "/robot/sensors/radar"})
        self.assertEqual(a._sensors["/robot/localization/pose"]["publisher_id"], "pose_selector")
        a._build_view()
        payload = copy.deepcopy(a.view["payload"])
        a._private["targets"][0]["pose"] = [123, 456, 0]
        a._build_view()
        self.assertEqual(payload, a.view["payload"])
        self.assertIsNone(a.campaign_status()["attempt"]["result"])
        status = a.finish_campaign()
        self.assertEqual(status["attempt"]["status"], "ended")
        self.assertIsNotNone(status["attempt"]["result"]["rmse_m"])
        tick = a.tick
        for _ in range(12):
            a.advance()
        self.assertEqual(a.tick, tick+12)
        self.assertEqual(a.campaign_status(), status)


if __name__ == "__main__":
    unittest.main()
