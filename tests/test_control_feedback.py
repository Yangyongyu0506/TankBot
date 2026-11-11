"""Control plots cannot disclose truth or bypass their independent display grants."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ("host","protocol","sdk/python")]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure,CampaignSession
from tankbot_host.control_feedback import ControlFeedback,SIGNALS
from tankbot_host.level_plugins import _validate,LevelValidationError
from tankbot_protocol.validation import Validator
from navigation_support import solution


class ControlFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.config=configure(load_config(ROOT/"config/game.yaml"),"navigation.c0")

    def test_native_feedback_has_full_sampling_history_and_matches_authorized_encoder_fk(self):
        a=Authority(self.config,controlled=True,startup_sources=solution(self.config));self.addCleanup(a.close)
        for _ in range(480):a.advance()
        points=a.campaign_status()["attempt"]["control_feedback"]["points"]
        self.assertGreater(len(points),60)
        self.assertEqual(points[0]["elapsed_ticks"],0)
        self.assertTrue(any(p["segment_index"]==1 for p in points))
        self.assertEqual(set(points[-1]["values"]),set(a.campaign.definition["permissions"]["visualization"]["allowed_control_signals"]))
        for p in points:
            v=p["values"];r=a.config["wheels"]["radius_m"];b=a.config["wheels"]["differential_track_m"]
            self.assertAlmostEqual(v["encoder_vx_mps"],r*(v["left_wheel_radps"]+v["right_wheel_radps"])/2)
            self.assertAlmostEqual(v["encoder_wz_radps"],r*(v["right_wheel_radps"]-v["left_wheel_radps"])/b)
        self.assertFalse(any(key in str(points) for key in ("truth_pose","truth_velocity","world")))
        delta=a.campaign_status(control_after_tick=points[-2]["simulation_tick"],run_id=a.run_id)["attempt"]["control_feedback"]
        self.assertFalse(delta["complete"])
        self.assertEqual(delta["points"],[points[-1]])
        self.assertLess(len(json.dumps(delta)),len(json.dumps(points))/10)
        reset=a.campaign_status(control_after_tick=points[-1]["simulation_tick"],run_id="previous-run")["attempt"]["control_feedback"]
        self.assertTrue(reset["complete"]);self.assertEqual(reset["points"],points)
        from tankbot_protocol.validation import Rejected
        for cursor in (-2,True,1.5,"1"):
            with self.subTest(cursor=cursor),self.assertRaisesRegex(Rejected,"INVALID_CURSOR"):
                a.campaign_status(control_after_tick=cursor,run_id=a.run_id)

    def test_history_is_bounded_and_voltage_obeys_clamp_exact_watchdog_and_revocation(self):
        spec=self.config["campaign"]["levels"]["navigation.c0"]
        spec["visualization"]["control_feedback"]["history_points"]=3
        feedback=ControlFeedback(self.config);session=CampaignSession(self.config);session.start(0)
        voltage={"simulation_tick":0,"payload":{"left_voltage_v":999.,"right_voltage_v":-999.}}
        feedback.command(voltage)
        def sample(tick):
            # Private truth is deliberately absent; only declared public inputs are provided.
            sensors={"/robot/sensors/joint_states":{"simulation_tick":tick,"payload":{"name":["left","right"],"velocity":[1.,2.]}},
                     "/robot/cmd_vel":{"payload":session.command(tick)}}
            feedback.sample(tick,sensors,session)
            return feedback.public()["points"][-1]["values"]
        limit=self.config["wheel_drive"]["max_voltage_v"]
        self.assertEqual(sample(0)["left_voltage_v"],limit)
        self.assertEqual(sample(6)["right_voltage_v"],-limit)
        timeout=int(self.config["wheel_drive"]["command_timeout_s"]*self.config["clock"]["physics_hz"])
        self.assertEqual(sample(timeout)["left_voltage_v"],0.)
        for tick in range(timeout+6,timeout+60,6):sample(tick)
        self.assertEqual(len(feedback.public()["points"]),3)
        feedback.command({**voltage,"simulation_tick":timeout+60});feedback.revoke()
        self.assertEqual(sample(timeout+60)["right_voltage_v"],0.)
        spec["permissions"]["visualization"]["allowed_control_signals"]=["encoder_vx_mps"]
        self.assertTrue(all(set(p["values"])=={"encoder_vx_mps"} for p in feedback.public()["points"]))

    def test_chart_source_units_permissions_and_resource_limits_are_validated(self):
        from tankbot_host.configuration import load_yaml
        original=load_yaml(ROOT/"levels/navigation.C0.yaml")
        cases=[
            (lambda d:d["permissions"]["visualization"].update(allowed_control_signals=[]),"visualization.control_feedback.charts[0].signals"),
            (lambda d:d["visualization"]["control_feedback"]["charts"][0].update(unit="V"),"visualization.control_feedback.charts[0].unit"),
            (lambda d:d["visualization"]["control_feedback"].update(history_points=999999),"visualization.control_feedback.history_points"),
            (lambda d:d["visualization"]["control_feedback"].update(period_ticks=3),"visualization.control_feedback.period_ticks"),
            (lambda d:d["permissions"]["visualization"]["view_policy"].update(local_observation_channels=[]),"visualization.control_feedback"),
        ]
        for change,path in cases:
            value=copy.deepcopy(original);change(value)
            with self.subTest(path=path),self.assertRaises(LevelValidationError) as raised:
                _validate(value,"temporary.yaml",self.config,Validator(self.config,"validation"))
            self.assertEqual(raised.exception.path,path)

    def test_old_lessons_do_not_get_ungranted_control_feedback(self):
        old=configure(self.config,"c2")
        feedback=ControlFeedback(old)
        self.assertIsNone(feedback.public())
