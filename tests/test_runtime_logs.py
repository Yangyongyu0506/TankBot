"""Bounded own-code feedback, including failed candidate startup and active exceptions."""
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/name) for name in ("host","protocol","sdk/python","runtime")]
from tankbot_host.authority import Authority,load_config
from tankbot_host.deployment import DeploymentManager
from tankbot_host.logs import RuntimeLogs
from tankbot_host.workspace import starter,digest
from browser_authority import BrowserSupervisor,runtime_event


class RuntimeLogTests(unittest.TestCase):
    def test_byte_bound_unicode_retention_drain_and_monotonic_sequence(self):
        logs=RuntimeLogs(2048)
        for _ in range(1000):logs.append("玩家输出 🙂\n"*10,source="runtime",tick=2)
        state=logs.public()
        self.assertGreater(state["dropped"],0)
        self.assertLessEqual(logs.bytes,2048)
        self.assertLess(len(state["entries"]),20)
        self.assertEqual(logs.drain()["entries"],state["entries"])
        self.assertEqual(logs.public()["entries"],[])
        self.assertEqual(logs.public()["next_sequence"],1000)

    def test_native_print_exception_and_candidate_errors_reach_management_status(self):
        config=load_config(ROOT/"config/game.yaml")
        sources=starter(config)
        sources["localization/odometry.py"]='''from tankbot import Module
class Odometry(Module):
    def setup(self, ctx):
        print("setup feedback 中文")
    def update(self, inputs, ctx):
        print("step feedback", ctx.simulation_tick)
        raise ValueError("intentional player failure")
'''
        a=Authority(config,controlled=True,startup_sources=sources)
        self.addCleanup(a.close)
        a.deployment=DeploymentManager(a)
        for _ in range(36):a.advance()
        text="".join(row["text"] for row in a.deployment.status()["logs"]["entries"])
        self.assertIn("setup feedback 中文",text)
        self.assertIn("step feedback",text)
        self.assertIn('File "localization/odometry.py", line 7',text)
        self.assertIn("ValueError: intentional player failure",text)
        self.assertNotIn("/tmp/tankbot-deployment-",text)
        self.assertTrue(a._faulted)
        files=starter(config);files["localization/odometry.py"]='print("candidate startup")\nraise RuntimeError("candidate failed")\n'
        snapshot={"files":files,"ledger":{}};snapshot["revision"]=digest(snapshot)
        a.deployment.start("test",snapshot)
        deadline=time.monotonic()+10
        while a.deployment.job and time.monotonic()<deadline:
            a.advance()
            if a.deployment.job and not a.deployment.job["worker"].ready:time.sleep(.002)
        self.assertIsNone(a.deployment.job)
        state=a.deployment.status()
        test_text="".join(row["text"] for row in state["logs"]["entries"] if row["source"]=="test")
        self.assertIn("candidate startup",test_text)
        self.assertIn("candidate failed",test_text)
        self.assertEqual(state["last"]["status"],"Failed")

    def test_browser_log_events_are_bounded_and_isolated_by_worker_identity(self):
        config=load_config(ROOT/"config/game.yaml");sent=[]
        with patch.dict(sys.modules,{"js":types.SimpleNamespace(runtime_send=lambda raw:sent.append(json.loads(raw)))}):
            worker=BrowserSupervisor(config,{"workspace":"/workspace"})
            try:
                runtime_event({"op":"log","worker_id":"other","text":"not mine"})
                runtime_event({"op":"log","worker_id":worker.worker_id,"text":'File "/tmp/tankbot-deployment-one/perception/tracker.py", line 8\n'})
                self.assertEqual(len(worker.logs.public()["entries"]),1)
                self.assertIn('"perception/tracker.py"',worker.logs.public()["entries"][0]["text"])
                self.assertEqual(sent[0]["value"]["max_log_bytes"],config["runtime"]["max_log_bytes"])
            finally:worker.close()


if __name__=="__main__":unittest.main()
