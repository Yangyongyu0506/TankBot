"""Twist references cannot bypass wheel voltage or come from another graph's outputs."""
from collections import deque
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python")]
from tankbot_host.authority import Authority, load_config
from tankbot_host.campaign import configure
from tankbot_host.robot_graph import GraphExecution
from tankbot_protocol.validation import Rejected, envelope


class NavigationReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load_config(ROOT / "config/game.yaml")

    def authority(self):
        authority = Authority(configure(self.base, "navigation.c2"), controlled=True)
        self.addCleanup(authority.close)
        return authority

    def reference(self, authority):
        return envelope("twist@1", "/robot/cmd_vel",
                        {"linear": {"x": .25, "y": 0., "z": 0.}, "angular": {"x": 0., "y": 0., "z": .5}},
                        tick=authority.tick, hz=authority.hz, run_id=authority.run_id,
                        publisher_id="module:reference", sequence=0, frame_id="base_link")

    def test_wheel_drive_references_are_explicitly_granted_and_never_reach_core_target(self):
        authority = self.authority()
        message = self.reference(authority)
        with self.assertRaisesRegex(Rejected, "UNAUTHORIZED"):
            authority.accept_graph_output("reference", message, activation_tick=authority.tick)
        grants = authority.campaign.definition["permissions"]["data_access"]
        grants["references"] = {"/robot/cmd_vel": "twist@1"}
        self.assertEqual(authority.graph_outputs()["/robot/cmd_vel"], "twist@1")
        authority.campaign.sequence = None  # Isolate reference routing from the existing fixed sequence.
        authority.accept_graph_output("reference", message, activation_tick=authority.tick)
        self.assertIsNone(authority._keyboard)
        self.assertEqual(authority._sensors["/robot/cmd_vel"], message)
        calls = []
        original = authority.core.call
        def record(command):
            calls.append(copy.deepcopy(command))
            return original(command)
        authority.core.call = record
        authority.advance()
        step = next(command for command in calls if command["op"] == "step")
        self.assertIsNone(step["target"])
        self.assertNotIn("wheel_voltage_target", step)
        self.assertEqual(authority._private["truth_pose"], authority.config["scene"]["initial_pose"])

    def test_graph_waits_for_its_own_writer_instead_of_an_old_deployment_reference(self):
        channel = "/robot/cmd_vel"
        reference = envelope("twist@1", channel,
                             {"linear": {"x": .25, "y": 0., "z": 0.}, "angular": {"x": 0., "y": 0., "z": 0.}},
                             tick=6, hz=60, run_id="reference-test", publisher_id="old-deployment",
                             sequence=0, frame_id="base_link")
        execution = {"mode": "periodic", "period_ticks": 6, "deadline_ticks": 6, "budget_ms": 1}
        graph = {"modules": {
            "source": {"contract": {"inputs": {}, "outputs": {"command": {"schema": "twist@1"}}, "execution": execution},
                       "input_channels": {}, "output_channels": {"command": channel}},
            "sink": {"contract": {"inputs": {"command": {"schema": "twist@1", "required": True, "max_age_ticks": 12}},
                                  "outputs": {}, "execution": execution},
                     "input_channels": {"command": channel}, "output_channels": {}},
        }}
        authority = SimpleNamespace(_sensors={channel: reference}, audit=deque(), delay=6, hz=60, run_id="reference-test")
        runtime = GraphExecution(authority, graph, 0)
        first = runtime.request(6)
        self.assertEqual([call["module_id"] for call in first["payload"]["modules"]], ["source"])
        self.assertEqual(first["payload"]["inputs"], [])
        runtime.cache[channel] = {**reference, "publisher_id": "this-deployment"}
        second = runtime.request(12)
        self.assertEqual([call["module_id"] for call in second["payload"]["modules"]], ["sink", "source"])
        self.assertEqual(second["payload"]["inputs"][0]["publisher_id"], "this-deployment")
