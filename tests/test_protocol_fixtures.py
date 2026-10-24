"""Run the documentation's protocol fixtures through the real M1 ingress validator."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"host"),str(ROOT/"protocol")]
from tankbot_host.authority import load_config
from tankbot_protocol.validation import Validator, Rejected


class ProtocolFixtureTests(unittest.TestCase):
    def test_documented_protocol_domain_failures(self):
        config = load_config(ROOT/"config/game.yaml")
        cases = json.loads((ROOT/"docs/examples/validation-cases.json").read_text())["cases"]
        supported = {"asymmetric-covariance","indefinite-covariance","wrong-time-formula","wrong-run","ungranted-publisher","forbidden-frame","differential-cannot-strafe","velocity-expired-at-controller","future-velocity-stamp","old-target-cannot-replace-newer"}
        for case in cases:
            if case["case_id"] not in supported:
                continue
            with self.subTest(case=case["case_id"]):
                msg = json.loads((ROOT/"docs/examples"/case["fixture"]).read_text())
                validator = Validator(config, "run-demo-001")
                grants = {(msg["publisher_id"],msg["channel"],msg["schema"],msg["frame_id"])}
                for mutation in case.get("mutations", [case.get("mutation")]):
                    if mutation is None:
                        continue
                    keys = mutation["pointer"].strip("/").split("/")
                    target = msg
                    for key in keys[:-1]:
                        target = target[key]
                    target[keys[-1]] = mutation["value"]
                context = case.get("context", {})
                if "last_target_tick" in context:
                    key = next(iter(grants))
                    validator.target_ticks[key] = context["last_target_tick"]
                    validator.sequences[key] = context["last_sequence_number"]
                with self.assertRaisesRegex(Rejected, case["expected_code"]):
                    validator.validate(msg,now=context.get("controller_tick",126),grants=grants)
