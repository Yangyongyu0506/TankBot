"""Behavioral M1 acceptance, physical checks, protocol boundary and real worker fault tests."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import http.client
import json
import math
import re
from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"host"), str(ROOT/"protocol"), str(ROOT/"sdk/python"), str(ROOT/"examples/robot")]
from tankbot_host.authority import Authority, CoreAdapter, load_config
from tankbot_host.server import LocalServer
from tankbot_protocol.validation import envelope, Validator, Rejected
from tankbot_protocol.wire import strict_loads, encode, receive
from tankbot import Pose2D, ModuleContext, JointState
from localization.kinematics import body_increment


def twist(v):
    return {"linear": {"x": v[0], "y": v[1], "z": 0}, "angular": {"x": 0, "y": 0, "z": v[2]}}


class M1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT/"config/m1.json")
        cls.config["weapons"]["enabled"] = False  # Preserve the M1 bare-chassis regression profile.

    def core(self, config=None, chassis=None):
        c = copy.deepcopy(config or self.config)
        core = CoreAdapter(c, chassis or c["scene"]["default_chassis"])
        self.addCleanup(core.close)
        return core

    def authority(self, config=None, controlled=True):
        authority = Authority(config or self.config, controlled=controlled)
        self.addCleanup(authority.close)
        return authority

    def test_servo_matches_force_equation_and_active_brake(self):
        c = copy.deepcopy(self.config)
        c["scene"]["walls"] = []
        core = self.core(c)
        command = c["motion_limits"]["max_vx_mps"]
        expected = 0.0
        dt = 1/(c["clock"]["physics_hz"]*c["clock"]["substeps"])
        mass, tau = c["body"]["mass_kg"], c["servo"]["tau_x_s"]
        drag = c["chassis"]["differential"]["drag_x_n_s_per_m"]
        cap = c["servo"]["max_force_x_n"]
        for _ in range(c["clock"]["substeps"]):
            force = max(-cap, min(cap, mass*(command-expected)/tau))-drag*expected
            expected += force/mass*dt
        out = core.call({"op": "step", "target": {"vx": command, "vy": 0, "wz": 0, "source_tick": 0}})
        self.assertAlmostEqual(out["truth_velocity"][0], expected, delta=c["validation"]["numeric_tolerance"])
        speed = out["truth_velocity"][0]
        out = core.call({"op": "step", "target": {"vx": 0, "vy": 0, "wz": 0, "source_tick": 1}})
        self.assertGreater(out["truth_velocity"][0], 0)
        self.assertLess(out["truth_velocity"][0], speed)

    def test_independent_inertia_and_target_saturation(self):
        c = copy.deepcopy(self.config)
        c["scene"]["walls"] = []
        core = self.core(c)
        out = core.call({"op": "step", "target": {"vx": 0, "vy": 0, "wz": c["motion_limits"]["max_wz_radps"]*2, "source_tick": 0}})
        expected = 0.0
        dt = c["solver"]["dt"]
        inertia = c["body"]["yaw_inertia_kg_m2"]
        for _ in range(c["clock"]["substeps"]):
            moment = c["servo"]["max_torque_nm"]-c["chassis"]["differential"]["drag_yaw_nm_s"]*expected
            expected += moment/inertia*dt
        self.assertAlmostEqual(out["truth_velocity"][2], expected, delta=c["validation"]["numeric_tolerance"])

    def test_both_chassis_and_radial_omni_inverse(self):
        core = self.core(chassis="omnidirectional")
        out = core.call({"op": "step", "target": {"vx": 0, "vy": 1, "wz": 0, "source_tick": 0}})
        out = core.call({"op": "step"})
        self.assertGreater(out["truth_pose"][1], 0)
        joints = out["sensors"]["joint_states"]
        dx, dy, da = body_increment(joints["name"], joints["velocity"], self.config["wheels"])
        self.assertAlmostEqual(dy, out["truth_velocity"][1], delta=self.config["validation"]["numeric_tolerance"])
        self.assertAlmostEqual(dx, 0, delta=self.config["validation"]["numeric_tolerance"])
        self.assertAlmostEqual(da, 0, delta=self.config["validation"]["numeric_tolerance"])
        differential = self.core()
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_MOTION"):
            differential.call({"op": "step", "target": {"vx": 0, "vy": 1, "wz": 0, "source_tick": 0}})

    def test_imu_acceleration_window_and_wheel_sampling(self):
        core = self.core()
        first = core.call({"op": "step", "target": {"vx": 1, "vy": 0, "wz": 0, "source_tick": 0}})
        self.assertIsNone(first["sensors"])
        out = core.call({"op": "step"})
        self.assertAlmostEqual(out["sensors"]["imu"]["linear_acceleration_x_mps2"], out["truth_velocity"][0]*self.config["clock"]["sensor_hz"], delta=self.config["validation"]["numeric_tolerance"])
        self.assertEqual(out["simulation_time_ns"], 2*1_000_000_000//self.config["clock"]["physics_hz"])
        self.assertEqual(out["sensors"]["joint_states"]["name"], ["left", "right"])

    def test_watchdog_uses_generation_time_and_does_not_reset_velocity(self):
        c = copy.deepcopy(self.config);c["scene"]["walls"] = []
        core = self.core(c)
        for tick in range(30):
            out = core.call({"op": "step", "target": {"vx": 1, "vy": 0, "wz": 0, "source_tick": 0} if tick == 0 else None})
        before = out["truth_velocity"][0]
        out = core.call({"op": "step"})
        self.assertGreater(out["truth_velocity"][0], 0)
        self.assertLess(out["truth_velocity"][0], before)
        for _ in range(120):
            out = core.call({"op": "step"})
        dt = c["solver"]["dt"]
        decay = 1-dt*(1/c["servo"]["tau_x_s"]+c["chassis"]["differential"]["drag_x_n_s_per_m"]/c["body"]["mass_kg"])
        expected = before*decay**(121*c["clock"]["substeps"])
        self.assertAlmostEqual(out["truth_velocity"][0], expected, delta=c["validation"]["numeric_tolerance"])

    def test_wall_stops_body_and_no_wheel_spin(self):
        core = self.core()
        poses = []
        for tick in range(self.config["validation"]["ticks"]):
            out = core.call({"op": "step", "target": {"vx": 1, "vy": 0, "wz": 0, "source_tick": tick}})
            poses.append(out["truth_pose"])
        wall = self.config["scene"]["walls"][-1]
        limit = wall["center"][0]-wall["size"][0]/2-self.config["body"]["length_m"]/2
        self.assertLessEqual(max(p[0] for p in poses), limit+self.config["validation"]["contact_measurement_tolerance_m"])
        self.assertLess(abs(out["truth_velocity"][0]), self.config["validation"]["numeric_tolerance"])
        self.assertLess(max(abs(v) for v in out["sensors"]["joint_states"]["velocity"]), self.config["validation"]["numeric_tolerance"])

    def test_600_tick_closed_loop_estimate_and_same_build_replay(self):
        a = self.authority()
        estimates = []
        for tick in range(self.config["validation"]["ticks"]):
            if tick % a.period == 0:
                a.keyboard(twist(self.config["validation"]["probe_target"]))
            a.advance()
            pose = a.view["payload"]["selected_pose"]
            if pose:
                estimates.append(pose)
        self.assertTrue(estimates)
        self.assertFalse([e for e in a.audit if e["event"] == "rejected"])
        for e in a.audit:
            if e["event"] == "pose_commit":
                self.assertEqual(e["tick"]-e["sample_tick"], a.delay)
        for estimate in estimates:
            truth = a.replay[estimate["simulation_tick"]]["truth_pose"]
            self.assertLess(math.hypot(estimate["pose"]["x_m"]-truth[0], estimate["pose"]["y_m"]-truth[1]), self.config["validation"]["odom_error_tolerance_m"])
        replay_core = self.core()
        for record in a.replay:
            self.assertEqual(replay_core.snapshot["truth_pose"], record["truth_pose"])
            self.assertEqual(replay_core.snapshot["truth_velocity"], record["truth_velocity"])
            replay_core.call({"op": "step", "target": record["target"]})
        self.assertEqual(replay_core.snapshot["truth_pose"], a._private["truth_pose"])

    def test_wrong_estimate_never_moves_truth_or_falls_back(self):
        config = copy.deepcopy(self.config)
        config["module"]["pose_offset_m"] = config["validation"]["pose_offset_m"]
        a = self.authority(config)
        for _ in range(30):
            a.advance()
        self.assertEqual(a._private["truth_pose"], config["scene"]["initial_pose"])
        self.assertEqual(a.view["payload"]["selected_pose"]["pose"]["x_m"], config["validation"]["pose_offset_m"])
        encoded = json.dumps(a.view)
        for field in ("truth", "world", "velocity_target", "initial_pose", "walls"):
            self.assertNotIn(field, encoded)

    def test_omnidirectional_600_tick_estimation(self):
        c = copy.deepcopy(self.config)
        c["scene"]["default_chassis"] = "omnidirectional"
        a = self.authority(c)
        target = c["validation"]["probe_target"]
        for tick in range(c["validation"]["ticks"]):
            if tick % a.period == 0:
                a.keyboard(twist((target[0], target[0], target[2])))
            a.advance()
            estimate = a.view["payload"]["selected_pose"]
            if estimate:
                truth = a.replay[estimate["simulation_tick"]]["truth_pose"]
                self.assertLess(math.hypot(estimate["pose"]["x_m"]-truth[0], estimate["pose"]["y_m"]-truth[1]), c["validation"]["odom_error_tolerance_m"])
        self.assertTrue(a.view["payload"]["selected_pose"])
        self.assertFalse([e for e in a.audit if e["event"] == "rejected"])

    def test_estimate_stales_and_hides_without_system_fallback(self):
        a = self.authority()
        for _ in range(25):
            a.advance()
        self.assertIsNotNone(a.view["payload"]["selected_pose"])
        # Trusted fault injection: stop future activations after a valid committed estimate.
        a._faulted = True
        a.worker.close()
        a._pending = None
        states = []
        for _ in range(self.config["view_policy"]["pose_hide_after_ticks"]+a.period):
            a.advance()
            selected = a.view["payload"]["selected_pose"]
            states.append(selected["freshness"] if selected else "hidden")
        self.assertIn("stale", states)
        self.assertEqual(states[-1], "hidden")

    def test_off_center_collision_transfers_angular_momentum(self):
        c = copy.deepcopy(self.config)
        wall = c["scene"]["walls"][-1]
        c["scene"]["initial_pose"][1] = wall["size"][1]/2+c["body"]["width_m"]/4
        core = self.core(c)
        max_wz = 0
        for tick in range(c["validation"]["ticks"]):
            out = core.call({"op": "step", "target": {"vx": 1, "vy": 0, "wz": 0, "source_tick": tick}})
            max_wz = max(max_wz, abs(out["truth_velocity"][2]))
        self.assertGreater(max_wz, c["validation"]["numeric_tolerance"])

    def test_output_faults_hide_pose(self):
        for fault, frame, error in (("no_output", "map", None), ("bad_covariance", "map", "INVALID_COVARIANCE"), ("none", "odom", "INVALID_FRAME"), ("exception", "map", "MODULE_ERROR")):
            with self.subTest(fault=fault, frame=frame):
                c = copy.deepcopy(self.config);c["module"].update(fault=fault, output_frame=frame)
                a = Authority(c, controlled=True)
                try:
                    for _ in range(60):
                        a.advance()
                    self.assertIsNone(a.view["payload"]["selected_pose"])
                    if error:
                        self.assertTrue(any(e.get("code") == error for e in a.audit))
                finally:
                    a.close()

    def test_external_watchdog_kills_infinite_loop_and_physics_continues(self):
        c = copy.deepcopy(self.config);c["module"]["fault"] = "infinite_loop"
        a = self.authority(c)
        started = time.monotonic()
        for _ in range(c["validation"]["ticks"]):
            a.advance()
        self.assertEqual(a.tick, c["validation"]["ticks"])
        self.assertIsNotNone(a.worker.proc.poll())
        self.assertIsNone(a.view["payload"]["selected_pose"])
        self.assertLess(time.monotonic()-started, c["runtime"]["startup_timeout_s"])

    def test_missed_commit_is_not_committed_later(self):
        a = self.authority(controlled=False)
        # Hold the worker at the OS scheduler while the authority advances its fixed gates.
        if sys.platform != "linux":
            self.skipTest("SIGSTOP fault injection is Linux-only")
        import os, signal
        os.kill(a.worker.proc.pid, signal.SIGSTOP)
        for _ in range(30):
            a.advance()
        self.assertTrue(any(e.get("code") in ("MISSED_DEADLINE", "RESOURCE_LIMIT") for e in a.audit))
        self.assertIsNone(a.view["payload"]["selected_pose"])

    def test_protocol_time_frame_psd_acl_and_sequence(self):
        v = Validator(self.config, "test")
        grant = {("module:odometry", "/robot/estimates/odometry/pose", "pose2d@1", "map")}
        msg = envelope("pose2d@1", "/robot/estimates/odometry/pose", {"x_m": 0, "y_m": 0, "yaw_rad": 0, "covariance": None, "child_frame_id": "base_link"}, tick=6, hz=60, run_id="test", publisher_id="module:odometry", sequence=0, frame_id="map")
        v.validate(msg, now=12, grants=grant)
        with self.assertRaisesRegex(Rejected, "OUT_OF_ORDER"):
            v.validate(msg, now=12, grants=grant)
        for key, value, code in (("run_id", "another", "WRONG_RUN"), ("simulation_time_ns", 1, "INVALID_TIMESTAMP"), ("frame_id", "odom", "INVALID_FRAME")):
            bad = copy.deepcopy(msg);bad[key] = value
            with self.assertRaisesRegex(Rejected, code):
                v.validate(bad, now=12, grants=grant)
        for bad in ((1,0,0,0,1,0,0,0,-1), (1,2,0,2,1,0,0,0,1), (1,0,0,0,1,1,0,0,1), (0,1e-6,0,1e-6,0,0,0,0,1)):
            with self.assertRaisesRegex(Rejected, "INVALID_COVARIANCE"):
                v.covariance(bad)
        v.covariance((1,1,0,1,1,0,0,0,0))

    def test_strict_json_and_immutable_sdk(self):
        for value in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'):
            with self.assertRaises(ValueError):
                strict_loads(value)
        pose = Pose2D(0,0,0)
        with self.assertRaises(FrozenInstanceError):
            pose.x_m = 1
        angles = [0.0]
        joint = JointState(["left"],angles,[0.0])
        angles[0] = 1.0
        self.assertEqual(joint.position,(0.0,))
        ctx = ModuleContext(6, .1, 12, {"nested": {"items": [1,2]}})
        with self.assertRaises(TypeError):
            ctx.config["nested"]["items"][0] = 3

    def test_documented_sdk_snippets_import_and_publish(self):
        source = (ROOT/"docs/05_ROBOT_MODULE_SYSTEM.md").read_text()
        ctx = ModuleContext(6, .1, 12, {})
        namespace = {"ctx":ctx}
        blocks = re.findall(r"^```python\n(.*?)^```", source, re.M|re.S)
        self.assertTrue(blocks)
        for code in blocks:
            exec(compile(code,"docs/05_ROBOT_MODULE_SYSTEM.md","exec"), namespace)
        self.assertTrue(ctx._outputs)
        self.assertEqual(ctx._outputs[-1][1], "twist@1")

    def test_selector_canonical_topic_and_gateway_privacy(self):
        a = self.authority()
        for _ in range(25):
            a.advance()
        self.assertEqual(a.selector.canonical["channel"], "/robot/localization/pose")
        self.assertEqual(a.selector.canonical["publisher_id"], "pose_selector")
        revision = a.view["payload"]["view_revision"]
        a._private["truth_pose"] = [100,100,1]
        a._build_view()
        self.assertEqual(a.view["payload"]["view_revision"], revision)
        self.assertEqual(a.view["payload"]["selected_pose"]["pose"]["x_m"], 0)
        self.assertNotIn("/system/pose", json.dumps(a.view))

    def test_overspeed_target_replacement_and_command_rate_limit(self):
        a = self.authority()
        limit = self.config["runtime"]["max_cmd_vel_per_sim_second"]
        for _ in range(limit-1):
            a.keyboard(twist((1,0,0)))
        a.keyboard(twist((0,0,0)))
        with self.assertRaisesRegex(Rejected,"RATE_LIMITED"):
            a.keyboard(twist((1,0,0)))
        a.advance()
        self.assertEqual(a._private["truth_velocity"],[0,0,0])
        core = self.core()
        target = self.config["motion_limits"]["max_vx_mps"]
        initial = core.call({"op":"step","target":{"vx":target*2,"vy":0,"wz":0,"source_tick":0}})
        comparison = self.core()
        clipped = comparison.call({"op":"step","target":{"vx":target,"vy":0,"wz":0,"source_tick":0}})
        self.assertEqual(initial, clipped)

    def test_missing_model_parameter_never_uses_default(self):
        for section, key in (("body", "mass_kg"), ("servo", "tau_x_s"), ("solver", "num_solver_iterations"), ("controller", "cmd_vel_timeout_s")):
            c = copy.deepcopy(self.config);del c[section][key]
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                self.core(c)

    def test_http_gateway_only_and_csrf_rejection(self):
        c = copy.deepcopy(self.config);c["host"]["port"] = 0
        a = self.authority(c)
        server = LocalServer(a)
        thread = threading.Thread(target=server.http.serve_forever, daemon=True);thread.start()
        self.addCleanup(server.http.server_close)
        self.addCleanup(server.http.shutdown)
        conn = http.client.HTTPConnection("127.0.0.1", server.http.server_port)
        self.addCleanup(conn.close)
        conn.request("GET", "/api/profile");response = conn.getresponse();profile = json.loads(response.read())
        self.assertEqual(profile["walls"], c["scene"]["walls"])
        for path in ("/api/truth", "/config/m1.json", "/../config/m1.json", "/api/world"):
            conn.request("GET", path);response = conn.getresponse();self.assertEqual(response.status,404);response.read()
        conn.request("POST", "/api/cmd_vel", json.dumps(twist((1,0,0))), {"Content-Type":"application/json"})
        response = conn.getresponse();self.assertEqual(response.status,403);response.read()
        conn.request("POST", "/api/cmd_vel", json.dumps(twist((1,0,0))), {"Content-Type":"application/json", "Origin":f"http://127.0.0.1:{server.http.server_port}", "X-TankBot-Control":profile["control_token"]})
        response = conn.getresponse();self.assertEqual(response.status,200);response.read()


if __name__ == "__main__":
    unittest.main()
