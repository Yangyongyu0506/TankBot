"""M5 graph admission and real isolated-process scheduling/transaction regressions."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/p) for p in ("host","protocol","sdk/python")]
from tankbot_host.authority import Authority,load_config
from tankbot_host.deployment import DeploymentManager,inspect_snapshot
from tankbot_host.workspace import WorkspaceStore,starter,digest
from tankbot_host.robot_graph import GraphExecution,bind_publishers,inspect_graph


SOURCE = '''from tankbot import Module, Pose2D
class Source(Module):
    def update(self, inputs, ctx):
        ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")
'''
SINK = '''from tankbot import Module, Pose2D
class Sink(Module):
    def update(self, inputs, ctx):
        value = inputs.latest("pose")
        ctx.publish("pose", Pose2D(value.data.x_m+100, 0, 0), frame_id="map",simulation_tick=value.simulation_tick)
'''


def graph_files(config):
    files = starter(config)
    files["nodes.py"] = SOURCE+SINK
    modules = []
    for mid,name in (("sink","Sink"),("source","Source")):
        contract = {"contract_version":"1.0","module_id":mid,"entry_point":"nodes:"+name,
                    "inputs":({"pose":{"schema":"pose2d@1","required":True,"max_age_ticks":18}} if mid=="sink" else {}),
                    "outputs":{"pose":{"schema":"pose2d@1"}},"execution":{"mode":"periodic","period_ticks":6,"deadline_ticks":6,"budget_ms":5},
                    "dependencies":["source"] if mid=="sink" else [],"state_version":"1"}
        files[f"contracts/{mid}.json"] = json.dumps(contract)
        modules.append({"module_id":mid,"contract":f"contracts/{mid}.json","config":{}})
    manifest = {"manifest_version":"1.0","sdk_version":"0.1.0","protocol_version":"1.0","project_id":"graph-test","entry_point":"nodes:Source",
                "modules":modules,"dependencies":[],"pose_source":{"mode":"player","module_id":"sink","fallback":"none"},
                "connections":[{"from":"source.pose","to":"/robot/modules/source/pose"},{"from":"/robot/modules/source/pose","to":"sink.pose"},
                               {"from":"sink.pose","to":"/robot/estimates/sink/pose"}]}
    files["tankbot.json"] = json.dumps(manifest)
    return files


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT/"config/game.yaml")
        self.a = Authority(self.config,controlled=True)
        self.addCleanup(self.a.close)
        self.a.deployment = DeploymentManager(self.a)

    def snapshot(self,files):
        snapshot={"files":files,"ledger":{}}
        snapshot["revision"]=digest(snapshot)
        return snapshot

    def finish(self):
        until=time.monotonic()+10
        while self.a.deployment.job and time.monotonic()<until:
            self.a.advance()
            if self.a.deployment.job and not self.a.deployment.job["worker"].ready:time.sleep(.002)
        self.assertIsNone(self.a.deployment.job,self.a.deployment.status())
        return self.a.deployment.last

    def deploy(self,files):
        snapshot=self.snapshot(files)
        self.a.deployment.start("test",snapshot);report=self.finish();self.assertEqual(report["status"],"Ready",report)
        self.a.deployment.start("deploy",snapshot);report=self.finish();self.assertEqual(report["status"],"Active",report)

    def test_graph_is_frozen_until_commit_and_pose_never_moves_physics(self):
        self.deploy(graph_files(self.config))
        self.assertEqual(next(m for m in self.a.graph.public()["modules"] if m["module_id"]=="sink")["waiting_inputs"],["pose"])
        a=self.a;requests=[];original=a.worker.submit
        def capture(request):requests.append(copy.deepcopy(request));return original(request)
        a.worker.submit=capture
        origin=a.graph.origin
        while a.tick <= origin+30:a.advance()
        first_sink=next(r for r in requests if any(m["module_id"]=="sink" for m in r["payload"]["modules"]))
        self.assertEqual(first_sink["payload"]["activation_tick"],origin+12)
        self.assertEqual(next(m for m in first_sink["payload"]["modules"] if m["module_id"]=="sink")["dt_ticks"],12)
        self.assertEqual(first_sink["payload"]["inputs"][0]["simulation_tick"],origin+6)
        self.assertEqual(a.view["payload"]["selected_pose"]["source_id"],"sink")
        self.assertGreater(a.view["payload"]["selected_pose"]["pose"]["x_m"],100)
        self.assertEqual(a._private["truth_pose"],self.config["scene"]["initial_pose"])
        self.assertTrue(all(e["tick"]-e.get("activation_tick",e["sample_tick"])==a.delay for e in a.audit if e["event"]=="pose_commit"))

    def test_type_permissions_writer_conflicts_dependencies_and_budget(self):
        for case in ("type","secret","writer","cycle","budget","async","command_input"):
            files=graph_files(self.config);manifest=json.loads(files["tankbot.json"])
            contract=json.loads(files["contracts/source.json"])
            if case=="type":
                sink=json.loads(files["contracts/sink.json"]);sink["inputs"]["pose"]["schema"]="imu@1";files["contracts/sink.json"]=json.dumps(sink)
            elif case=="secret":manifest["connections"][1]["from"]="/world/truth"
            elif case=="writer":manifest["connections"].append(copy.deepcopy(manifest["connections"][0]))
            elif case=="cycle":contract["dependencies"]=["sink"]
            elif case=="budget":contract["execution"]["budget_ms"]=100
            elif case=="async":files["nodes.py"]=files["nodes.py"].replace("def update","async def update")
            elif case=="command_input":
                sink=json.loads(files["contracts/sink.json"]);sink["inputs"]["pose"]["schema"]="fire_command@1";files["contracts/sink.json"]=json.dumps(sink)
            files["contracts/source.json"]=json.dumps(contract);files["tankbot.json"]=json.dumps(manifest)
            with self.subTest(case=case):
                if case=="async":
                    self.a.deployment.start("test",self.snapshot(files));self.assertEqual(self.finish()["status"],"Failed")
                else:
                    with self.assertRaises(ValueError):inspect_snapshot(self.snapshot(files),self.a)

    def test_bad_module_does_not_drop_sibling_outputs_and_stops_after_failure_limit(self):
        files=graph_files(self.config)
        source=json.loads(files["contracts/source.json"]);source["outputs"]["pose"]["schema"]="pose2d@1"
        sink=json.loads(files["contracts/sink.json"]);sink["inputs"]={};sink["dependencies"]=[]
        files["contracts/sink.json"]=json.dumps(sink)
        manifest=json.loads(files["tankbot.json"]);manifest["connections"].pop(1)
        manifest["connections"][0]["to"]="/robot/estimates/source/pose";manifest["pose_source"]["module_id"]="source"
        files["tankbot.json"]=json.dumps(manifest)
        files["nodes.py"]=SOURCE+'''from tankbot import Module, Pose2D
class Sink(Module):
    def update(self, inputs, ctx):
        if ctx.simulation_tick < 10000:
            ctx.publish("pose", Pose2D(0,0,0),frame_id="map")
        else:
            raise ValueError("bad module")
'''
        self.deploy(files)
        # Inject a correctly framed worker result with a module-domain error after Test.
        finish=self.a.worker.finish
        def invalid(**kwargs):
            result=finish(**kwargs)
            if result:
                publisher=self.a.graph.graph["modules"]["sink"]["publisher_id"]
                for msg in result["payload"]["outputs"]:
                    if msg["publisher_id"]==publisher:msg["frame_id"]="odom"
            return result
        self.a.worker.finish=invalid
        for _ in range(40):self.a.advance()
        self.assertEqual(self.a.graph.faults,{"sink":"INVALID_FRAME"})
        self.assertGreater(self.a._candidates["source"]["payload"]["x_m"],0)
        self.assertFalse(self.a._faulted)

    def test_event_inputs_only_trigger_on_new_samples_and_dt_accumulates_after_skips(self):
        files=graph_files(self.config)
        sink=json.loads(files["contracts/sink.json"]);sink["execution"]={"mode":"event","trigger_inputs":["pose"],"min_interval_ticks":6,"deadline_ticks":6,"budget_ms":5}
        files["contracts/sink.json"]=json.dumps(sink)
        self.deploy(files)
        captured=[];submit=self.a.worker.submit
        def record(request):captured.append(copy.deepcopy(request));return submit(request)
        self.a.worker.submit=record
        for _ in range(60):self.a.advance()
        events=[r for r in captured if any(m["module_id"]=="sink" for m in r["payload"]["modules"])]
        tokens=[next(m["sequence_number"] for m in r["payload"]["inputs"] if m["channel"]=="/robot/modules/source/pose") for r in events]
        self.assertGreater(len(tokens),1)
        self.assertEqual(len(tokens),len(set(tokens)))

    def test_graph_reset_uses_activation_origin_and_rollback_restarts_whole_graph(self):
        files = graph_files(self.config)
        files["nodes.py"] = files["nodes.py"].replace('class Source(Module):', '''class Source(Module):
    def reset(self, ctx, reason):
        self.origin = ctx.simulation_tick
''').replace('Pose2D(ctx.simulation_tick, 0, 0)', 'Pose2D(self.origin, 0, 0)')
        self.deploy(files)
        initial = self.a.deployment.active["sha256"]
        origin = self.a.graph.origin
        for _ in range(25):self.a.advance()
        self.assertEqual(self.a._candidates["sink"]["payload"]["x_m"], origin+100)
        worker = self.a.worker
        bad = copy.deepcopy(files);bad["nodes.py"] += '\nraise RuntimeError("candidate failure")\n'
        self.a.deployment.start("test",self.snapshot(bad))
        self.assertEqual(self.finish()["status"],"Failed")
        self.assertIs(self.a.worker,worker)
        changed = copy.deepcopy(files);changed["nodes.py"] += '\n# new version\n'
        self.deploy(changed)
        self.assertIsNot(self.a.worker,worker)
        self.a.deployment.start("rollback",sha256=initial)
        self.assertEqual(self.finish()["status"],"Active")
        new_origin = self.a.graph.origin
        self.assertGreater(new_origin,origin)
        for _ in range(25):self.a.advance()
        self.assertEqual(self.a._candidates["sink"]["payload"]["x_m"],new_origin+100)

    def test_explicit_pose_source_switch_clears_revision_and_never_changes_truth(self):
        files = graph_files(self.config)
        contract = json.loads(files["contracts/source.json"])
        contract["outputs"]["candidate"] = {"schema":"pose2d@1"}
        files["contracts/source.json"] = json.dumps(contract)
        manifest = json.loads(files["tankbot.json"])
        manifest["connections"].append({"from":"source.candidate","to":"/robot/estimates/source/pose"})
        files["tankbot.json"] = json.dumps(manifest)
        files["nodes.py"] = files["nodes.py"].replace('ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")',
            'ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")\n        ctx.publish("candidate", Pose2D(-7, 8, 1), frame_id="map")')
        self.deploy(files)
        for _ in range(30):self.a.advance()
        revision,truth = self.a.view_revision,copy.deepcopy(self.a._private)
        self.a.select_pose_source("source")
        self.assertEqual(self.a.view_revision,revision+1)
        selected = self.a.view["payload"]["selected_pose"]
        self.assertEqual(selected["source_id"],"source")
        self.assertEqual(selected["pose"]["x_m"],-7)
        self.assertEqual(self.a._private,truth)
        with self.assertRaises(ValueError):self.a.select_pose_source("unknown")
        self.a.graph.faults["source"] = "TEST_STOPPED"
        for _ in range(self.config["view_policy"]["pose_hide_after_ticks"]+30):self.a.advance()
        self.assertIsNone(self.a.view["payload"]["selected_pose"])
        self.assertEqual(self.a.selector.source_id,"source")

    def test_one_infinite_callback_terminates_robot_batch_while_physics_continues(self):
        files = graph_files(self.config)
        threshold = self.a.tick+600
        files["nodes.py"] = files["nodes.py"].replace('ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")',
            f'if ctx.simulation_tick >= {threshold}:\n            while True: pass\n        ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")')
        self.deploy(files)
        while self.a.tick < threshold+60:self.a.advance()
        self.assertTrue(self.a._faulted)
        self.assertIsNotNone(self.a.worker.fault)
        self.assertEqual(self.a.core.snapshot["tick"],self.a.tick)
        old = self.a.tick
        for _ in range(30):self.a.advance()
        self.assertEqual(self.a.tick,old+30)

    def test_registered_velocity_topic_decodes_to_typed_input(self):
        files = graph_files(self.config)
        self.a.config["control_sources"]["turret"] = "robot"
        source = json.loads(files["contracts/source.json"])
        source["outputs"]["velocity"] = {"schema":"turret_velocity@1"}
        sink = json.loads(files["contracts/sink.json"])
        sink["inputs"]["velocity"] = {"schema":"turret_velocity@1","required":True,"max_age_ticks":18}
        files["contracts/source.json"] = json.dumps(source);files["contracts/sink.json"] = json.dumps(sink)
        manifest = json.loads(files["tankbot.json"])
        manifest["connections"] += [{"from":"source.velocity","to":"/robot/turret/cmd_vel"},
                                    {"from":"/robot/turret/cmd_vel","to":"sink.velocity"}]
        files["tankbot.json"] = json.dumps(manifest)
        files["nodes.py"] = 'from tankbot import TurretVelocity\n'+files["nodes.py"].replace(
            'ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")',
            'ctx.publish("pose", Pose2D(ctx.simulation_tick, 0, 0), frame_id="map")\n        ctx.publish("velocity",TurretVelocity(1.2),frame_id="base_link")').replace(
            'value = inputs.latest("pose")','assert inputs.latest("velocity").data.velocity_radps == 1.2\n        value = inputs.latest("pose")')
        self.deploy(files)
        for _ in range(30):self.a.advance()
        self.assertEqual(self.a.graph.faults,{})
        self.assertIn("sink",self.a._candidates)
