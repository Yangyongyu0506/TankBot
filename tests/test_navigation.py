"""Confirmed wheel-voltage plant, fixed command challenge and chapter isolation."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ("host","protocol","sdk/python")]
from tankbot_host.authority import Authority,CoreAdapter,load_config
from tankbot_host.campaign import configure,CampaignSession
from tankbot_host.deployment import DeploymentManager
from tankbot_host.level_plugins import LevelValidationError
from tankbot_host.scene_definition import SceneResolver,resolve_scene
from tankbot_host.workspace import starter,workspace_scope
from tankbot_host.workspace_api import WorkspaceAPI,select_workspace
from tankbot_protocol.validation import Rejected,Validator,envelope
from navigation_support import solution


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.base=load_config(ROOT/"config/game.yaml")
        self.config=configure(self.base,"navigation.c0")

    def authority(self,files=None):
        a=Authority(self.config,controlled=True,startup_sources=files)
        self.addCleanup(a.close)
        return a

    def run_to_end(self,a):
        for _ in range(a.campaign.limit_ticks+10*a.period):
            a.advance()
            if a.campaign.status!="active":return
        self.fail("attempt never reached a terminal outcome")

    def test_reference_control_completes_at_exact_end_and_terminal_state_freezes(self):
        a=self.authority(solution(self.config))
        revision=a.view_revision
        self.assertIsNone(a.campaign.started_tick)
        self.run_to_end(a)
        self.assertTrue(a.campaign.result["passed"],a.campaign.result)
        self.assertEqual(a.tick-a.campaign.started_tick,a.campaign.sequence_ticks)
        self.assertEqual(a.view_revision,revision)
        result=a.campaign.result;parameters=a.campaign.definition["rules"]["parameters"]
        self.assertLessEqual(result["origin_distance_m"],parameters["max_origin_distance_m"])
        self.assertGreaterEqual(result["path_length_m"],parameters["min_path_length_m"])
        before=copy.deepcopy(a._private);tick=a.tick
        for _ in range(60):a.advance()
        self.assertEqual(a._private,before);self.assertEqual(a.tick,tick)
        self.assertIsNone(a._private["turret_state"])
        self.assertEqual(a._private["targets"],[])
        self.assertEqual(a._private["projectiles"],[])

    def test_zero_output_fails_actual_path_gate_even_when_origin_error_is_zero(self):
        a=self.authority(starter(self.config));self.run_to_end(a)
        self.assertEqual(a.campaign.result["reason"],"trajectory_failed")
        self.assertEqual(a.campaign.result["origin_distance_m"],0.)
        self.assertEqual(a.campaign.result["path_length_m"],0.)

    def test_bad_return_has_native_traceback_and_fails_without_waiting_forever(self):
        files=starter(self.config)
        files["control/wheel_controller.py"]=files["control/wheel_controller.py"].replace("return voltage_v","return np.zeros(3, dtype=np.float64)")
        a=self.authority(files);self.run_to_end(a)
        self.assertEqual(a.campaign.result["reason"],"controller_error")
        self.assertLess(a.tick,a.campaign.limit_ticks)
        text="".join(entry["text"] for entry in a.logs.public()["entries"])
        self.assertIn("Traceback (most recent call last):",text)
        self.assertIn("TypeError",text)

    def test_command_boundaries_deployment_arming_and_no_restart_of_clock(self):
        c=CampaignSession(self.config)
        for tick in (0,120,1000):
            self.assertEqual(c.command(tick)["linear"]["x"],.5)
            self.assertIsNone(c.outcome({"truth_pose":[0,0,0],"targets":[]},tick))
        c.start(100,{"motion_metrics":{"path_length_m":2.}})
        self.assertEqual(c.command(339)["linear"]["x"],.5)
        self.assertEqual(c.command(340)["angular"]["z"],self.config["campaign"]["levels"]["navigation.c0"]["rules"]["command_sequence"]["segments"][1]["twist"]["angular"]["z"])
        self.assertEqual(c.command(460)["linear"]["x"],.5)
        self.assertEqual(c.command(1540)["linear"]["x"],0.)
        self.assertEqual(c.command(1540)["angular"]["z"],0.)
        c.start(800,{"motion_metrics":{"path_length_m":9.}})
        self.assertEqual(c.started_tick,100);self.assertEqual(c.path_origin_m,2.)

    def test_both_terminal_thresholds_are_inclusive_and_checked_together(self):
        parameters=self.config["campaign"]["levels"]["navigation.c0"]["rules"]["parameters"]
        distance=parameters["max_origin_distance_m"];length=parameters["min_path_length_m"]
        delta=self.config["validation"]["numeric_tolerance"]
        for x,path,expected in ((distance,length,"objective_completed"),(distance+delta,length,"trajectory_failed"),(distance,length-delta,"trajectory_failed")):
            with self.subTest(distance=x,path=path):
                session=CampaignSession(self.config);session.start(0)
                private={"truth_pose":[x,0.,0.],"targets":[],"player_alive":True,"motion_metrics":{"path_length_m":path}}
                self.assertEqual(session.outcome(private,session.sequence_ticks),expected)

    def test_voltage_clamping_turn_sign_inertia_and_watchdog_braking(self):
        def core(c=None):
            value=CoreAdapter(c or self.config,"differential");self.addCleanup(value.close);return value
        a,b=core(),core();limit=self.config["wheel_drive"]["max_voltage_v"]
        for tick in range(12):
            for instance,u in ((a,limit),(b,limit*10)):
                instance.call({"op":"step","wheel_voltage_target":{"left_voltage_v":u,"right_voltage_v":u,"source_tick":tick}})
            self.assertEqual(a.snapshot,b.snapshot)
        turn=core();s=turn.call({"op":"step","wheel_voltage_target":{"left_voltage_v":-1.,"right_voltage_v":1.,"source_tick":0}})
        self.assertGreater(s["truth_velocity"][2],0.)
        s=turn.call({"op":"step"})
        self.assertLess(s["sensors"]["joint_states"]["velocity"][0],0.)
        heavy=copy.deepcopy(self.config);heavy["wheel_drive"]["wheel_inertia_kg_m2"]*=10
        slow=core(heavy);fast=core()
        request={"op":"step","wheel_voltage_target":{"left_voltage_v":1.,"right_voltage_v":1.,"source_tick":0}}
        self.assertLess(slow.call(request)["truth_velocity"][0],fast.call(request)["truth_velocity"][0])
        stale,explicit=core(),core();stop=int(self.config["wheel_drive"]["command_timeout_s"]*self.config["clock"]["physics_hz"])
        for tick in range(stop+20):
            for instance in (stale,explicit):
                request={"op":"step"}
                if tick==0:request["wheel_voltage_target"]={"left_voltage_v":limit,"right_voltage_v":limit,"source_tick":0}
                if instance is explicit and tick==stop:request["wheel_voltage_target"]={"left_voltage_v":0.,"right_voltage_v":0.,"source_tick":tick}
                instance.call(request)
            self.assertEqual(stale.snapshot,explicit.snapshot)

    def test_input_grants_do_not_give_manual_drive_or_pose_access(self):
        a=self.authority()
        self.assertEqual(set(a.runtime_inputs()),{"/robot/cmd_vel","/robot/sensors/joint_states"})
        with self.assertRaises(Rejected):a.keyboard({"linear":{"x":1.,"y":0.,"z":0.},"angular":{"x":0.,"y":0.,"z":0.}})
        with self.assertRaises(Rejected):a.turret_keyboard({"velocity_radps":1.})
        self.assertIsNotNone(a.view["payload"]["selected_pose"])
        self.assertNotIn("/robot/localization/pose",a.runtime_inputs())
        for lid in ("c0","c1","c2","c3","c4","c5"):
            old=configure(self.config,lid)
            self.assertNotIn("wheel_drive",old)
            self.assertTrue(old["weapons"]["enabled"])

    def test_invalid_motor_values_and_ungranted_motion_feedback_are_rejected(self):
        for field,value in (("resistance_ohm",0.),("wheel_inertia_kg_m2",-1.),("max_voltage_v",float("nan"))):
            invalid=copy.deepcopy(self.config);invalid["wheel_drive"][field]=value
            with self.subTest(field=field),self.assertRaises(Rejected):resolve_scene(invalid)
        session=CampaignSession(self.config);session.start(0)
        session.definition["permissions"]["visualization"]["allowed_metrics"]=[]
        self.assertNotIn("origin_distance_m",session.public()["motion"])
        self.assertNotIn("path_length_m",session.public()["motion"])

    def test_wheel_voltage_envelope_permissions_frames_and_exact_expiry(self):
        validator=Validator(self.config,"drive-run")
        msg=envelope("wheel_voltage@1","/robot/wheels/cmd_voltage",{"left_voltage_v":1.,"right_voltage_v":-1.},
                     tick=0,hz=self.config["clock"]["physics_hz"],run_id="drive-run",publisher_id="module:drive",sequence=0,frame_id="base_link")
        grant={("module:drive","/robot/wheels/cmd_voltage","wheel_voltage@1","base_link")}
        validator.validate(msg,now=0,grants=grant,consume=False)
        with self.assertRaisesRegex(Rejected,"UNAUTHORIZED"):validator.validate(msg,now=0,grants=set())
        bad=copy.deepcopy(msg);bad["frame_id"]="map"
        with self.assertRaises(Rejected):validator.validate(bad,now=0,grants=grant)
        expires=int(self.config["wheel_drive"]["command_timeout_s"]*self.config["clock"]["physics_hz"])
        with self.assertRaisesRegex(Rejected,"STALE_DATA"):validator.validate(msg,now=expires,grants=grant)

    def test_scene_retry_and_workspace_switch_keep_both_projects_and_histories(self):
        resolver=SceneResolver(resolve_scene(self.config))
        self.assertIs(resolver.get("navigation.c0"),resolver.get("navigation.c0"))
        with tempfile.TemporaryDirectory() as directory,patch("tankbot_host.workspace.ROOT",Path(directory)):
            weapons=WorkspaceAPI(configure(self.base,"c2"))
            old=weapons.store.read();weapons.store.edit(old["revision"],{"perception/tracker.py":"# authored KF\n"})
            before={p.name:p.read_bytes() for p in weapons.store.directory.glob("*.json")}
            scopes={workspace_scope(weapons.config):weapons}
            nav=select_workspace(self.config,scopes)
            self.assertNotIn("perception/tracker.py",nav.store.read()["files"])
            original=nav.store.read();nav.store.edit(original["revision"],{"control/wheel_controller.py":"# authored drive\n"})
            self.assertIs(select_workspace(configure(self.base,"c2"),scopes),weapons)
            self.assertEqual({p.name:p.read_bytes() for p in weapons.store.directory.glob("*.json")},before)
            self.assertIs(select_workspace(self.config,scopes),nav)
            self.assertEqual(nav.store.read()["files"]["control/wheel_controller.py"],"# authored drive\n")
