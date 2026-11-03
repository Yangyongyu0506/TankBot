"""Odometry time alignment, information boundaries, grading and source preservation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ("host","protocol","sdk/python")]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure,CampaignSession
from tankbot_host.workspace import starter
from tankbot_host.workspace_api import WorkspaceAPI
from navigation_support import solution


class NavigationOdometryTests(unittest.TestCase):
    def setUp(self):
        self.base=load_config(ROOT/"config/game.yaml")
        self.config=configure(self.base,"navigation.c1")

    def authority(self,files=None):
        a=Authority(self.config,controlled=True,startup_sources=files)
        self.addCleanup(a.close)
        return a

    def run_to_end(self,a):
        for _ in range(a.campaign.limit_ticks+10*a.period):
            a.advance()
            if a.campaign.status!="active":return
        self.fail("odometry challenge did not finish")

    def test_reference_integrator_passes_without_pose_input_and_freezes_estimated_view(self):
        a=self.authority(solution(self.config))
        self.assertIsNone(a.view["payload"]["selected_pose"])
        self.assertEqual(set(a.runtime_inputs()),{"/robot/cmd_vel","/robot/sensors/joint_states"})
        self.run_to_end(a)
        r=a.campaign.result;p=a.campaign.definition["rules"]["parameters"]
        self.assertTrue(r["passed"],r)
        self.assertLessEqual(r["rmse_m"],p["max_position_rmse_m"])
        self.assertLessEqual(r["yaw_rmse_rad"],p["max_yaw_rmse_rad"])
        self.assertGreaterEqual(r["scored_samples"],p["required_estimates"])
        self.assertEqual(a.tick-a.campaign.started_tick,a.campaign.sequence_ticks)
        pose=a.view["payload"]["selected_pose"]
        self.assertEqual(pose["source_id"],"odometry")
        private=copy.deepcopy(a._private)
        for _ in range(30):a.advance()
        self.assertEqual(a._private,private);self.assertEqual(a.view["payload"]["selected_pose"],pose)
        self.assertLessEqual(len(a._self_pose_history),self.config["runtime"]["estimate_history_ticks"]+1)
        self.assertNotIn("_self_pose_history",json.dumps(a.campaign_status()))

    def test_stationary_estimate_cannot_pass_on_final_return_to_origin(self):
        files=solution(self.config)
        files["localization/odometry.py"]=starter(self.config)["localization/odometry.py"]
        a=self.authority(files);self.run_to_end(a)
        p=a.campaign.definition["rules"]["parameters"];r=a.campaign.result
        self.assertEqual(r["reason"],"estimation_failed")
        self.assertLessEqual(r["origin_distance_m"],p["max_origin_distance_m"])
        self.assertGreaterEqual(r["path_length_m"],p["min_path_length_m"])
        self.assertGreater(r["rmse_m"],p["max_position_rmse_m"])

    def test_same_sample_truth_is_used_and_duplicates_unknown_times_and_other_sources_do_not_score(self):
        a=self.authority()
        a.campaign.start(0)
        a._self_pose_history[6]=[1.,2.,.3]
        message={"schema":"pose2d@1","channel":"/robot/estimates/odometry/pose","simulation_tick":6,
                 "frame_id":"map","payload":{"x_m":1.,"y_m":2.,"yaw_rad":.3,"covariance":None,"child_frame_id":"base_link"}}
        a.accept_graph_output("odometry",message,activation_tick=6)
        self.assertEqual(a.campaign.diagnostics.report()["rmse_m"],0.)
        self.assertEqual(a.campaign.diagnostics.report()["yaw_rmse_rad"],0.)
        a.accept_graph_output("odometry",message,activation_tick=6)
        message["simulation_tick"]=12
        a.accept_graph_output("odometry",message,activation_tick=12)
        self.assertEqual(a.campaign.estimates,1)
        a._self_pose_history[12]=[1.,2.,.3]
        message["frame_id"]="odom"
        a.accept_graph_output("odometry",message,activation_tick=12)
        self.assertEqual(a.campaign.estimates,1)  # An unaligned odom frame is not map truth.
        message["frame_id"]="map"
        message["simulation_tick"]=18;message["channel"]="/robot/estimates/other/pose"
        a._self_pose_history[18]=[1.,2.,.3]
        a.accept_graph_output("other",message,activation_tick=18)
        self.assertEqual(a.campaign.estimates,1)

    def test_bad_odometry_shape_has_python_traceback_and_fails_promptly(self):
        files=solution(self.config)
        files["localization/odometry.py"]=files["localization/odometry.py"].replace("return self.pose.copy()","return np.zeros(2, dtype=np.float64)")
        a=self.authority(files);self.run_to_end(a)
        self.assertEqual(a.campaign.result["reason"],"controller_error")
        self.assertLess(a.tick,a.campaign.limit_ticks)
        output="".join(entry["text"] for entry in a.logs.public()["entries"])
        self.assertIn("Traceback (most recent call last):",output)
        self.assertIn("odometry_module.py",output)
        self.assertIn("shape=(3,)",output)

    def test_biased_pose_is_displayed_without_affecting_ground_truth_motion(self):
        files=solution(self.config)
        files["localization/odometry.py"]=files["localization/odometry.py"].replace("return self.pose.copy()","return self.pose + np.array([2.,0.,0.],dtype=np.float64)")
        a=self.authority(files)
        for _ in range(90):a.advance()
        selected=a.view["payload"]["selected_pose"]
        self.assertEqual(selected["source_id"],"odometry")
        self.assertGreater(selected["pose"]["x_m"]-a._private["truth_pose"][0],1.)
        feedback=a.campaign.public()["live_metrics"]
        self.assertGreater(feedback["rmse_m"],1.)
        self.assertIn("yaw_rmse_rad",feedback)
        self.assertNotIn("/robot/localization/pose",a.graph_inputs())

    def test_unlock_preserves_authored_controller_and_both_course_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(configure(self.base,"navigation.c0"),directory=directory)
            old=api.store.read();authored="# authored Navigation controller\n"+solution(api.config)["control/wheel_controller.py"]
            api.store.edit(old["revision"],{"control/wheel_controller.py":authored})
            before=api.store.read()
            state=api.unlock(self.config)
            self.assertEqual(state["snapshot"]["files"]["control/wheel_controller.py"],authored)
            self.assertIn("localization/odometry.py",state["snapshot"]["files"])
            self.assertEqual(api.store.read(before["revision"])["files"],before["files"])
            self.assertTrue(state["learning"]["upgrade_required"])
            plan=api.post("upgrade",{"revision":state["snapshot"]["revision"]})
            self.assertNotIn("control/wheel_controller.py",[entry["path"] for entry in plan["entries"]])
            upgraded=api.post("apply",{"plan_id":plan["plan_id"],"revision":state["snapshot"]["revision"],
                                       "resolutions":{entry["path"]:"incoming" for entry in plan["entries"]}})
            self.assertFalse(api.get()["learning"]["upgrade_required"])
            self.assertEqual(upgraded["files"]["control/wheel_controller.py"],authored)
            api.unlock(configure(self.base,"navigation.c0"))
            self.assertEqual(api.store.read()["files"]["control/wheel_controller.py"],authored)
            self.assertIn("localization/odometry.py",api.store.read()["files"])

    def test_live_error_permissions_are_independent_and_missing_samples_cannot_pass(self):
        session=CampaignSession(self.config);session.start(0)
        session.definition["permissions"]["visualization"]["allowed_metrics"]=["rmse_m"]
        self.assertEqual(set(session.public()["live_metrics"]),{"rmse_m","scored_samples"})
        # A moving robot with no estimates still fails, even with a perfect endpoint.
        private={"truth_pose":[0.,0.,0.],"targets":[],"motion_metrics":{"path_length_m":8.}}
        self.assertEqual(session.outcome(private,session.sequence_ticks),"estimation_failed")
