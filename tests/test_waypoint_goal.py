"""Public mission targets are typed references, not robot observations or actuators."""
import copy
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python", "runtime")]
from tankbot import Inputs, Module, ModuleContext, Twist, WaypointGoal
from tankbot_host.authority import load_config
from tankbot_protocol.validation import Validator, Rejected, envelope
from module_runner import ModuleRunner


class WaypointGoalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config/game.yaml")

    def message(self):
        return envelope("waypoint_goal@1", "/robot/navigation/goal",
                        {"goal_index": 0, "position_m": [2., 0.]},
                        tick=6, hz=60, run_id="waypoint-test", publisher_id="waypoint_route",
                        sequence=0, frame_id="map")

    def test_schema_and_grants_reject_extra_state_and_invalid_targets(self):
        message = self.message()
        validator = Validator(self.config, "waypoint-test")
        grants = {("waypoint_route", "/robot/navigation/goal", "waypoint_goal@1", "map")}
        validator.validate(message, now=6, grants=grants, consume=False)
        for field, value in (("goal_index", -1), ("goal_index", True), ("position_m", [1., 2., 3.]),
                             ("position_m", [float("nan"), 0.]), ("position_m", ["1", "2"]), ("truth_pose", [0., 0., 0.])):
            bad = copy.deepcopy(message)
            bad["payload"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Rejected):
                validator.validate(bad, now=6, grants=grants, consume=False)
        for field, value in (("frame_id", "base_link"), ("channel", "/robot/cmd_vel"), ("message_type", "command")):
            bad = copy.deepcopy(message)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(Rejected):
                validator.validate(bad, now=6, grants=grants, consume=False)
        with self.assertRaisesRegex(Rejected, "UNAUTHORIZED"):
            validator.validate(message, now=6, grants=set())

    def test_sdk_owns_immutable_numpy_coordinates_and_cannot_publish_a_goal(self):
        source = np.array([2., 0.], dtype=np.float64)
        goal = WaypointGoal(0, source)
        source[0] = 99.
        self.assertEqual(goal.position_m.tolist(), [2., 0.])
        self.assertEqual(goal.position_m.dtype, np.float64)
        with self.assertRaises(ValueError):
            goal.position_m.setflags(write=True)
        for index in (-1, True, .5):
            with self.subTest(index=index), self.assertRaises(ValueError):
                WaypointGoal(index, [2., 0.])
        for coordinates in ([1.], [1., float("inf")]):
            with self.assertRaises(ValueError):
                WaypointGoal(0, coordinates)
        with self.assertRaises(TypeError):
            WaypointGoal(0, ["1", "2"])
        with self.assertRaises(TypeError):
            ModuleContext(6, .1, 12, {}).publish("goal", goal, frame_id="map")

    def test_runner_decodes_a_goal_without_world_or_robot_state(self):
        class Probe(Module):
            def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
                self.goal = inputs.latest("goal")
                self.asserted_type = isinstance(self.goal.data, WaypointGoal)
                ctx.publish("command", Twist(), frame_id="base_link")
        runner = object.__new__(ModuleRunner)
        runner.init = {"config": {}, "physics_hz": 60, "run_id": "waypoint-test", "publisher_id": "module:probe",
                       "input_channels": {"goal": "/robot/navigation/goal"}, "output_channels": {"command": "/robot/cmd_vel"}}
        runner.contract = {"module_id": "probe", "outputs": {"command": {"schema": "twist@1"}}}
        runner.init["contract"] = runner.contract
        runner.sequence = 0
        runner.module = Probe()
        request = {"payload": {"activation_tick": 6, "output_commit_tick": 12, "step_id": "step-6",
                               "modules": [{"module_id": "probe", "dt_ticks": 6}], "inputs": [self.message()]}}
        response = runner.step(request)
        self.assertTrue(runner.module.asserted_type)
        self.assertEqual(runner.module.goal.frame_id, "map")
        self.assertEqual(runner.module.goal.simulation_tick, 6)
        self.assertEqual(response["payload"]["outputs"][0]["schema"], "twist@1")
