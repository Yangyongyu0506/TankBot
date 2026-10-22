"""M1b behavioral tests against the real native core and isolated Python worker."""
import copy
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"host"),str(ROOT/"protocol"),str(ROOT/"sdk/python")]
from tankbot_host.authority import CoreAdapter, load_config


class WeaponTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/"config/m1.json")

    def core(self, config=None):
        core=CoreAdapter(config or self.config,(config or self.config)["scene"]["default_chassis"])
        self.addCleanup(core.close)
        return core

    def test_turret_torque_has_opposite_chassis_reaction(self):
        c=copy.deepcopy(self.config)
        c["clock"]["physics_hz"]*=c["clock"]["substeps"]
        c["clock"]["substeps"]=1
        core=self.core(c)
        rate=c["weapons"]["turret"]["max_relative_rate_radps"]/4
        out=core.call({"op":"step","turret_target":{"velocity_radps":rate,"source_tick":0}})
        base_wz=out["truth_velocity"][2]
        turret_wz=out["turret_state"]["relative_rate_radps"]+base_wz
        self.assertLess(base_wz,0)
        self.assertGreater(turret_wz,0)
        momentum=c["body"]["yaw_inertia_kg_m2"]*base_wz+c["weapons"]["turret"]["yaw_inertia_kg_m2"]*turret_wz
        self.assertAlmostEqual(momentum,0,delta=c["validation"]["numeric_tolerance"])

    def test_added_turret_mass_changes_translation_without_servo_compensation(self):
        core=self.core()
        bare=copy.deepcopy(self.config);bare["weapons"]["enabled"]=False
        bare_core=self.core(bare)
        request={"op":"step","target":{"vx":self.config["motion_limits"]["max_vx_mps"],"vy":0,"wz":0,"source_tick":0}}
        loaded=core.call(request);unloaded=bare_core.call(request)
        self.assertGreater(loaded["truth_velocity"][0],0)
        self.assertLess(loaded["truth_velocity"][0],unloaded["truth_velocity"][0])
        self.assertEqual(loaded["turret_state"]["relative_angle_rad"],0)

    def test_turret_continuous_rotation_and_separate_joint_sample(self):
        core=self.core()
        for tick in range(self.config["clock"]["physics_hz"]*2):
            out=core.call({"op":"step","turret_target":{"velocity_radps":self.config["weapons"]["turret"]["max_relative_rate_radps"],"source_tick":tick}})
        self.assertGreater(out["turret_state"]["relative_angle_rad"],2*math.pi)
        self.assertEqual(out["sensors"]["joint_states"]["name"],["left","right"])
        self.assertEqual(out["sensors"]["turret_joint_states"]["name"],["turret_joint"])

    def test_turret_watchdog_brakes_without_velocity_reset(self):
        core=self.core()
        rate=self.config["weapons"]["turret"]["max_relative_rate_radps"]/4
        timeout=int(self.config["weapons"]["turret"]["cmd_vel_timeout_s"]*self.config["clock"]["physics_hz"])
        for tick in range(timeout):
            out=core.call({"op":"step","turret_target":{"velocity_radps":rate,"source_tick":0} if tick==0 else None})
        before=out["turret_state"]["relative_rate_radps"]
        out=core.call({"op":"step"})
        self.assertGreater(out["turret_state"]["relative_rate_radps"],0)
        self.assertLess(out["turret_state"]["relative_rate_radps"],before)

    def shot(self, core, request_id, tick=None):
        tick=core.snapshot["tick"] if tick is None else tick
        return core.call({"op":"step","fire_requests":[{"publisher_id":"test","request_id":request_id,"source_tick":tick}]})

    def authority(self,config=None):
        from tankbot_host.authority import Authority
        a=Authority(config or self.config,controlled=True)
        self.addCleanup(a.close)
        return a

    def test_cooldown_rejection_boundary_and_idempotence(self):
        core=self.core()
        first=self.shot(core,"first")
        self.assertEqual(first["weapon_state"]["shots_fired"],1)
        cooldown=round(self.config["weapons"]["firing"]["cooldown_s"]*self.config["clock"]["physics_hz"])
        rejected=self.shot(core,"early")
        self.assertEqual(rejected["fire_results"][0][1]["status"],"cooldown")
        while core.snapshot["tick"]<cooldown-1:core.call({"op":"step"})
        out=self.shot(core,"almost")
        self.assertEqual(out["fire_results"][0][1]["status"],"cooldown")
        out=self.shot(core,"boundary")
        self.assertEqual(out["weapon_state"]["shots_fired"],2)
        duplicate=self.shot(core,"first")
        self.assertEqual(duplicate["weapon_state"]["shots_fired"],2)
        self.assertEqual(duplicate["fire_results"][0][1],first["fire_results"][0][1])
        # A rejected ID remains rejected after cooling down; it is never queued for later firing.
        while core.snapshot["tick"]<cooldown*2:core.call({"op":"step"})
        duplicate=self.shot(core,"early")
        self.assertEqual(duplicate["fire_results"][0][1]["status"],"cooldown")
        self.assertEqual(duplicate["weapon_state"]["shots_fired"],2)

    def test_blocked_entire_barrel_has_no_recoil_or_cooldown(self):
        c=copy.deepcopy(self.config)
        c["scene"]["walls"]=[{"center":[0.2,0],"size":[0.02,1]}]
        core=self.core(c)
        out=self.shot(core,"blocked")
        self.assertEqual(out["weapon_state"]["last_result"]["status"],"blocked")
        self.assertTrue(out["weapon_state"]["ready"])
        self.assertEqual(out["projectiles"],[])
        self.assertFalse(any(e["kind"]=="fired" for e in out["weapon_events"]))
        # Geometry overlaps in this deliberate blocking fixture: compare against the same no-shot world.
        comparison=self.core(c).call({"op":"step"})
        self.assertEqual(out["truth_velocity"],comparison["truth_velocity"])

    def test_target_hit_and_static_chassis_contact(self):
        c=copy.deepcopy(self.config)
        c["scene"]["initial_pose"][2]=-math.pi
        core=self.core(c)
        out=self.shot(core,"at-target")
        distance=abs(c["weapons"]["targets"][0]["pose"][0]-c["scene"]["initial_pose"][0])
        flight_ticks=math.ceil(distance/c["weapons"]["projectile"]["relative_speed_mps"]*c["clock"]["physics_hz"])
        for _ in range(flight_ticks):out=core.call({"op":"step"})
        self.assertEqual(out["target_hits"]["target_01"],1)
        self.assertEqual(out["projectiles"],[])
        for tick in range(out["tick"],240):
            out=core.call({"op":"step","target":{"vx":1,"vy":0,"wz":0,"source_tick":tick}})
        gap=out["truth_pose"][0]-(-3+c["body"]["length_m"])
        self.assertGreater(gap,-c["validation"]["contact_measurement_tolerance_m"])
        self.assertLess(abs(out["truth_velocity"][0]),c["validation"]["contact_measurement_tolerance_m"])

    def test_no_dedup_eviction_and_queue_is_bounded(self):
        c=copy.deepcopy(self.config);c["weapons"]["firing"]["request_cache_capacity"]=1
        core=self.core(c)
        first=self.shot(core,"one")
        self.assertEqual(self.shot(core,"two")["fire_results"][0][1]["status"],"resource_limit")
        self.assertEqual(self.shot(core,"one")["fire_results"][0][1],first["fire_results"][0][1])
        c["weapons"]["firing"]["pending_capacity"]=1
        core=self.core(c)
        with self.assertRaisesRegex(ValueError,"queue full"):
            core.call({"op":"step","fire_requests":[{"publisher_id":"test","request_id":x,"source_tick":0} for x in ("a","b")]})

    def test_python_weapon_control_fixed_gate_and_all_actuator_replay(self):
        c=copy.deepcopy(self.config)
        c["module"]["entry_point"]="weapon_demo:WeaponDemo"
        c["module"]["weapon_demo"]["enabled"]=True
        c["control_sources"].update(turret="robot",weapon="robot")
        a=self.authority(c)
        from tankbot_protocol.validation import Rejected
        with self.assertRaisesRegex(Rejected,"UNAUTHORIZED"):a.turret_keyboard({"velocity_radps":1})
        with self.assertRaisesRegex(Rejected,"UNAUTHORIZED"):a.fire_keyboard({"request_id":"manual"})
        for _ in range(180):a.advance()
        self.assertFalse([e for e in a.audit if e["event"]=="rejected"])
        self.assertGreater(a._private["weapon_state"]["shots_fired"],0)
        self.assertGreater(a._private["turret_state"]["relative_angle_rad"],0)
        first=next(r for r in a.replay if r["actuators"]["fire_requests"])
        self.assertEqual(first["tick"],c["module"]["weapon_demo"]["fire_period_ticks"]+c["runtime"]["commit_delay_ticks"])
        replay=self.core(c)
        for record in a.replay:replay.call(record["actuators"])
        self.assertEqual(replay.snapshot,a._private)

    def test_estimated_gateway_is_independent_of_private_weapon_truth(self):
        import json
        a=self.authority()
        for _ in range(30):a.advance()
        before=copy.deepcopy(a.gateway.build(a.tick,a.view_revision,a.selector,a._sensors))
        a._private["truth_pose"]=[99,99,1]
        a._private["projectiles"]=[{"invalid":"should never be inspected"}]
        a._private["target_hits"]={"secret":99}
        a._build_view()
        self.assertEqual(before,a.view["payload"])
        self.assertEqual(a.view["schema"],"view_snapshot@1")
        self.assertEqual(a.view["payload"]["objects"],[])
        self.assertNotIn("target_id",json.dumps(a.view))

    def test_practice_grants_truth_to_view_but_not_robot(self):
        c=copy.deepcopy(self.config);c["view_mode"]="weapons-practice";c["view_policy"]=c["practice_view_policy"]
        a=self.authority(c)
        captured=[];submit=a.worker.submit
        def capture(request):
            captured.append(copy.deepcopy(request));return submit(request)
        a.worker.submit=capture
        a.fire_keyboard({"request_id":"practice"})
        for _ in range(8):a.advance()
        self.assertEqual(a.view["schema"],"view_snapshot@2")
        self.assertEqual(a.view["payload"]["selected_pose"]["source_id"],"system")
        self.assertTrue(any(o["kind"]=="projectile" for o in a.view["payload"]["objects"]))
        for request in captured:
            self.assertEqual({m["schema"] for m in request["payload"]["inputs"]},{"imu@1","joint_state@1","weapon_state@1"})
            self.assertFalse(any(m["channel"] in ("/view/snapshot","/robot/localization/pose") for m in request["payload"]["inputs"]))
        bad=copy.deepcopy(c);bad["view_mode"]="estimated"
        from tankbot_host.authority import Authority
        with self.assertRaisesRegex(ValueError,"cannot grant truth"):Authority(bad)

    def test_manual_sdk_types_and_feedback_are_strict(self):
        from dataclasses import FrozenInstanceError
        from tankbot import ModuleContext,TurretVelocity,WeaponState
        from tankbot_protocol.validation import Validator,Rejected,envelope
        ctx=ModuleContext(6,.1,12,{})
        ctx.publish("turret_velocity",TurretVelocity(2),frame_id="base_link")
        request_id=ctx.fire(request_id="fire-once")
        self.assertEqual(request_id,"fire-once")
        self.assertEqual(ctx._outputs[-1][1],"turret_velocity@1")
        with self.assertRaises(FrozenInstanceError):WeaponState(True,0,0,0,None).ready=False
        v=Validator(self.config,"test")
        for schema,channel,payload,frame,kind in (("turret_velocity@1","/robot/turret/cmd_vel",{"velocity_radps":2},"base_link","topic"),("fire_command@1","/robot/weapons/cannon/fire",{},None,"command")):
            msg=envelope(schema,channel,payload,tick=0,hz=60,run_id="test",publisher_id="ui",sequence=0,frame_id=frame,message_type=kind,request_id="one" if kind=="command" else None)
            grant={("ui",channel,schema,frame)}
            v.validate(msg,now=0,grants=grant,consume=False)
            with self.assertRaisesRegex(Rejected,"STALE_DATA"):v.validate(msg,now=30,grants=grant)
            bad=copy.deepcopy(msg);bad["payload"]["truth_pose"]=[0,0,0]
            with self.assertRaisesRegex(Rejected,"INVALID_SCHEMA"):v.structure(bad)

    def test_http_weapon_routes_validate_identity_csrf_and_idempotence(self):
        import http.client,json,threading
        from tankbot_host.server import LocalServer
        c=copy.deepcopy(self.config);c["host"]["port"]=0
        a=self.authority(c);server=LocalServer(a)
        thread=threading.Thread(target=server.http.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.http.server_close);self.addCleanup(server.http.shutdown)
        connection=http.client.HTTPConnection("127.0.0.1",server.http.server_port);self.addCleanup(connection.close)
        headers={"Content-Type":"application/json","Origin":f"http://127.0.0.1:{server.http.server_port}","X-TankBot-Control":server.token}
        for path,payload in (("/api/turret_cmd_vel",{"velocity_radps":2}),("/api/fire",{"request_id":"http-one"})):
            connection.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
            response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request("POST",path,json.dumps(payload),headers)
            response=connection.getresponse();self.assertEqual(response.status,200);response.read()
        a.advance()
        connection.request("POST","/api/fire",json.dumps({"request_id":"http-one"}),headers)
        response=connection.getresponse();self.assertEqual(response.status,200)
        self.assertEqual(json.loads(response.read())["status"],"fired")
        a.advance();self.assertEqual(a._private["weapon_state"]["shots_fired"],1)

    def test_invalid_actuator_output_rejects_entire_batch(self):
        from tankbot_protocol.validation import envelope
        a=self.authority()
        # Trusted adversarial response injection at the supervisor boundary.
        a.tick=12
        a._pending={"step_id":"step-6","activation":6,"commit":12}
        pose=envelope("pose2d@1",a.output_channels["pose"],{"x_m":1,"y_m":0,"yaw_rad":0,"covariance":None,"child_frame_id":"base_link"},tick=6,hz=a.hz,run_id=a.run_id,publisher_id=a.publisher_id,sequence=0,frame_id="map")
        fire=envelope("fire_command@1","/robot/weapons/cannon/fire",{},tick=6,hz=a.hz,run_id=a.run_id,publisher_id=a.publisher_id,sequence=1,message_type="command",request_id="forbidden")
        # Permit a second declared output slot; the fire channel still has no grant.
        a.contract["outputs"]["extra"]={"schema":"pose2d@1"}
        response=envelope("runtime_step_result@1","/runtime/step",{"step_id":"step-6","results":[{"module_id":a.contract["module_id"],"status":"completed","error_code":None}],"outputs":[pose,fire]},tick=6,hz=a.hz,run_id=a.run_id,publisher_id="runtime",sequence=2,message_type="service_response",request_id="step-6")
        a.worker.finish=lambda **kwargs:response
        a._commit()
        self.assertIsNone(a.selector.canonical)
        self.assertFalse(a._fire_pending)
        self.assertEqual(a.audit[-1]["code"],"UNAUTHORIZED")

    def test_missing_weapon_parameters_never_use_defaults(self):
        for section,key in (("turret","mass_kg"),("turret","cmd_vel_timeout_s"),("projectile","radius_m"),("firing","cooldown_s"),("numerics","spatial_epsilon_m")):
            c=copy.deepcopy(self.config);del c["weapons"][section][key]
            with self.subTest(section=section,key=key),self.assertRaises(ValueError):self.core(c)

    def test_documented_weapon_sdk_example_executes(self):
        import re
        from tankbot import ModuleContext
        ctx=ModuleContext(18,.1,24,{})
        source=(ROOT/"docs/14_WEAPONS_DESIGN.md").read_text()
        for code in re.findall(r'^```python\n(.*?)^```',source,re.M|re.S):exec(compile(code,'docs/14_WEAPONS_DESIGN.md','exec'),{'ctx':ctx})
        self.assertEqual(ctx._outputs[-1][1],"turret_velocity@1")
        self.assertEqual(ctx._commands,[("fire","shot-18")])
