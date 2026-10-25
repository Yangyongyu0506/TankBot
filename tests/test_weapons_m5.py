"""M5 Weapons curriculum: authorized numerical algorithms and physical boundaries."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("host", "protocol", "sdk/python")]
from tankbot import AimInput, TargetPoints, TargetPoseEstimate
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure, RadarSimulator
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.deployment import DeploymentManager
from tankbot_protocol.message import envelope
from tankbot_protocol.validation import Validator, Rejected
from weapons_support import solutions


class WeaponsM5Tests(unittest.TestCase):
    def config(self, level):
        return configure(load_config(ROOT / "config/game.yaml"), level)

    def test_two_numerical_methods_complete_c3_and_c4_from_authorized_inputs(self):
        evidence = []
        for level in ("c3", "c4"):
            for kind in ("kalman", "window"):
                with self.subTest(level=level, method=kind):
                    config = self.config(level)
                    a = Authority(config, controlled=True, startup_sources=solutions(config, kind))
                    try:
                        for _ in range(round(config["campaign"]["levels"][level]["time_limit_s"] * a.hz)):
                            a.advance()
                            if a.campaign.status in ("passed", "ended"):
                                break
                        status = a.campaign_status()
                        evidence.append({"level":level,"method":kind,"tick":a.tick,"result":status,
                                         "module_faults":a.graph.faults,"worker_fault":a.worker.fault})
                        print(json.dumps(evidence[-1], ensure_ascii=False), flush=True)
                        self.assertEqual(a.campaign.status, "passed", evidence[-1])
                        self.assertEqual(a.graph.faults, {})
                        self.assertEqual(a.view["payload"]["objects"], [])
                        self.assertEqual(a.view["payload"]["effects"], [])
                    finally:
                        a.close()
        path = ROOT / ".m1-cache/m5-weapons-evidence.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))

    def test_stage_permissions_and_center_only_information(self):
        zero = {"linear":{"x":1.,"y":0.,"z":0.},"angular":{"x":0.,"y":0.,"z":0.}}
        for level in ("c1", "c2", "c3", "c4"):
            a = Authority(self.config(level), controlled=True)
            try:
                with self.assertRaises(ValueError): a.keyboard(zero)
                if level in ("c3", "c4"):
                    with self.assertRaises(ValueError): a.turret_keyboard({"velocity_radps":1.})
                    with self.assertRaises(ValueError): a.fire_keyboard({"request_id":"manual"})
                profile = a.public_profile()
                encoded = json.dumps(profile)
                self.assertNotIn("waypoints_m", encoded)
                self.assertNotIn("truth_pose", encoded)
                self.assertEqual(a.view["payload"]["selected_pose"]["source_id"], "system")
                if level == "c4":
                    self.assertTrue(a.config["weapons"]["targets"][0]["armor"])
                    # Rotating a target around its center must not reveal yaw in the radar.
                    r1, r2 = RadarSimulator(a.config), RadarSimulator(a.config)
                    private = {"truth_pose":[0,0,0],"targets":[{"target_id":"secret","pose":[-4.5,-2,0],"alive":True}]}
                    rotated = copy.deepcopy(private);rotated["targets"][0]["pose"][2] = 1.4
                    self.assertEqual(r1.sample(private, 6), r2.sample(rotated, 6))
            finally: a.close()

    def test_c2_to_c4_upgrade_preserves_all_algorithms_and_uses_graph_version(self):
        with tempfile.TemporaryDirectory() as directory:
            api = WorkspaceAPI(self.config("c2"), directory=directory)
            current = api.get()["snapshot"]
            changes = {"perception/transforms.py":"# preserved SE3\n", "perception/tracker.py":"# preserved tracker\n"}
            api.post("save", {"revision":current["revision"],"changes":changes})
            for level in ("c3", "c4"):
                view = api.unlock(self.config(level));snapshot = view["snapshot"]
                self.assertTrue(view["learning"]["upgrade_required"],level)
                for path, source in changes.items():self.assertEqual(snapshot["files"][path], source)
                plan = api.post("upgrade", {"revision":snapshot["revision"]})
                self.assertFalse(any(entry["path"] in changes for entry in plan["entries"]))
                self.assertEqual(plan["template_version"], "2.0.0")
                managed = set(view["learning"]["managed_files"])
                current = api.post("apply", {"revision":plan["base_revision"],"plan_id":plan["plan_id"],
                    "resolutions":{e["path"]:"incoming" if e["path"] in managed else "keep" for e in plan["entries"]}})
                self.assertFalse(api.get()["learning"]["upgrade_required"])
                for path, source in changes.items(): self.assertEqual(current["files"][path],source)

    def test_target_pose_schema_frames_age_psd_and_numpy_shapes(self):
        config = self.config("c4")
        channel = "/robot/estimates/tracking/target_pose"
        msg = envelope("target_pose_estimate@1", channel, {"x_m":1.,"y_m":2.,"yaw_rad":.3,"covariance":np.eye(3).ravel().tolist()},
                       tick=6,hz=60,run_id="test",publisher_id="module:tracking",sequence=1,frame_id="map")
        grants = {("module:tracking",channel,"target_pose_estimate@1","map")}
        Validator(config,"test").validate(msg, now=12, grants=grants,source_tick=6)
        bad = copy.deepcopy(msg);bad["payload"]["covariance"][0] = -1.
        with self.assertRaisesRegex(Rejected,"INVALID_COVARIANCE"): Validator(config,"test").validate(bad,now=12,grants=grants)
        bad = copy.deepcopy(msg);bad["frame_id"]="odom"
        with self.assertRaises(Rejected): Validator(config,"test").validate(bad,now=12,grants=grants)
        with self.assertRaisesRegex(Rejected,"STALE_DATA"): Validator(config,"test").validate(msg,now=100,grants=grants)
        value = TargetPoseEstimate(1.,2.,.3,np.eye(3))
        self.assertEqual(value.covariance.shape,(3,3))
        self.assertFalse(value.covariance.flags.writeable)
        self.assertEqual(TargetPoints([]).positions_m.shape,(0,2))
        with self.assertRaises(ValueError): TargetPoints(np.zeros((3,3)))
        with self.assertRaises(ValueError): AimInput(np.zeros(3),0.,np.zeros(3),0.,0.,False)

    def test_config_rejects_inconsistent_chapters_armor_and_actuator_grants(self):
        from tankbot_host.campaign import validate_profile
        config = load_config(ROOT / "config/game.yaml")
        for case in ("order","armor","grant","profile"):
            c = copy.deepcopy(config)
            if case == "order":c["campaign"]["chapters"][1]["levels"].reverse()
            if case == "armor":c["campaign"]["levels"]["c4"]["target"].pop("armor")
            if case == "grant":c["robot_graph"]["profiles"]["weapons_auto"]["grants"]["actuators"]["/robot/cmd_vel"]="twist@1"
            if case == "profile":c["campaign"]["levels"]["c3"]["robot_profile"]="missing"
            with self.subTest(case=case),self.assertRaises(ValueError):validate_profile(c)
