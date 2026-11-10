"""Trusted Pyodide adapters. Loaded ONLY in the Core Worker, never in the robot bundle."""
from collections import deque
import json
import hashlib
import time
import uuid
from tankbot_protocol.wire import strict_loads
from tankbot_host.authority import Authority, load_config, core_configuration
from tankbot_host.logs import RuntimeLogs
from tankbot_host.execution_profiles import select_execution_profile


class WasmCore:
    def __init__(self, config, chassis, binary=None):
        from js import core_build_sha256
        self.build_sha256 = str(core_build_sha256)
        self.snapshot = self.call({"op":"init", "config":core_configuration(config), "chassis":chassis})

    def call(self, request):
        from js import core_call
        result = strict_loads(core_call(json.dumps(request, allow_nan=False)))
        if not result["ok"]:
            raise ValueError(result["error"])
        self.snapshot = result["data"]
        return self.snapshot

    def close(self):
        pass


class BrowserSupervisor:
    workers = {}
    runtime_backend = "pyodide"

    def __init__(self, config, init, *, deferred=False, execution_profile=None):
        self.execution_profile = execution_profile or select_execution_profile(config, self.runtime_backend)
        if self.execution_profile.backend != self.runtime_backend:
            raise ValueError("RUNTIME_PROFILE_BACKEND")
        self.worker_id = uuid.uuid4().hex
        self.workers[self.worker_id] = self
        self.ready = False
        self.startup_result = None
        self.detail = None
        self.limit = config["runtime"]["max_message_bytes"]
        self.logs = RuntimeLogs(config["runtime"]["max_log_bytes"])
        self.budget = self.execution_profile.batch_wall_deadline_ms/1000
        self.budget_ns = self.execution_profile.wall_deadline_ns
        from tankbot_host.runtime_timing import RuntimeTiming
        self.timing=RuntimeTiming(self.execution_profile.batch_wall_deadline_ms,self.runtime_backend,
                                  profile=self.execution_profile.public())
        self.batch_times_ms = deque(maxlen=config["runtime"]["history_limit_ticks"])
        self.fault = None
        self.active = self.result = None
        self.expires_ns = None
        self.closed = False
        self.send("init", {"init":init,"limit":self.limit,"budget_ms":self.budget*1000,
                           "batch_wall_deadline_ns":self.budget_ns,
                           "max_log_bytes": config["runtime"]["max_log_bytes"],
                           "probe":config["browser"]["probe_enabled"],
                           "startup_timeout_s":config["browser"]["startup_timeout_s"]})

    def send(self, op, value):
        from js import runtime_send
        started=time.monotonic_ns()
        raw=json.dumps({"op":op,"value":value,"worker_id":self.worker_id}, allow_nan=False)
        encoded=time.monotonic_ns()
        runtime_send(raw)
        return (encoded-started)/1_000_000,(time.monotonic_ns()-encoded)/1_000_000

    def poll_ready(self):
        return self.ready

    def submit(self, request):
        if self.closed or self.fault or self.active:
            return False
        self.active = request["request_id"]
        self.started_ns = time.monotonic_ns()
        self.expires_ns = self.started_ns+self.budget_ns
        self.result = None
        self.timing.begin(request,started_ns=self.started_ns)
        encoded,written=self.send("step", request)
        self.timing.sent(request_encode_ms=encoded,request_write_ms=written)
        return True

    def receive(self, raw, elapsed_ms, transport=None):
        try:
            if self.closed or self.active is None or self.result is not None:
                raise ValueError("Unsolicited runtime output")
            arrived=time.monotonic_ns()
            if arrived > self.expires_ns:
                # Preserve the late arrival as evidence, without accepting its output.
                self.timing.sent(response_arrival_ms=(arrived-self.started_ns)/1_000_000,
                                 bridge_round_trip_ms=elapsed_ms)
                self.fault="RESOURCE_LIMIT"
                self.timing.finish(self.fault,"wall_deadline")
                self.close()
                return
            if not isinstance(raw,str) or len(raw.encode()) > self.limit:
                raise ValueError("Size")
            decoded=time.monotonic_ns()
            result = strict_loads(raw)
            received=time.monotonic_ns()
            self.timing.received(result,received_ns=received,response_decode_ms=(received-decoded)/1_000_000,
                                 response_decode_started_monotonic_ns=decoded,bridge_round_trip_ms=elapsed_ms)
            # The Authority clock is final. A delayed bridge watchdog cannot grant time,
            # and parsing a large response cannot straddle the deadline unnoticed.
            if received > self.expires_ns:
                self.fault="RESOURCE_LIMIT"
                self.timing.finish(self.fault,"response_decode_deadline")
                self.close()
                return
            self.result = result
            self.batch_times_ms.append((received-self.started_ns)/1_000_000)
        except (ValueError, TypeError, RecursionError):
            self.fault = "RESOURCE_LIMIT"
            self.timing.finish(self.fault,"receive_validation")
            self.close()

    def finish(self, *, controlled=False):
        # Never wait on this Worker. The browser event loop delivers results between ticks.
        result = self.result
        self.active = self.result = None
        if self.fault or result is None:
            expired=self.expires_ns is not None and time.monotonic_ns()>self.expires_ns
            if self.fault is None:self.fault="RESOURCE_LIMIT" if expired else "MISSED_DEADLINE"
            self.timing.finish(self.fault,"wall_deadline" if self.fault=="RESOURCE_LIMIT" else "commit_gate",at_gate=True)
            self.close()
            return None
        self.timing.finish(at_gate=True)
        return result

    def close(self):
        if not self.closed:
            self.closed = True
            self.timing.finish(self.fault or "CANCELLED","worker_close")
            self.send("close", {})
            self.workers.pop(self.worker_id, None)


def runtime_event(event):
    worker = BrowserSupervisor.workers.get(event.get("worker_id"))
    if worker is None:
        return
    if event["op"] == "ready":
        worker.ready = True
        worker.startup_result = {"ready": True, "unit_tests": event.get("unit_tests", 0), "runtime_packages": event.get("runtime_packages", {})}
    elif event["op"] == "result":
        worker.receive(event["raw"], event["elapsed_ms"], event.get("transport"))
    elif event["op"] == "log":
        import re
        text = str(event.get("text", ""))[:2048]
        text = re.sub(r"/tmp/tankbot-deployment-[^/]+/", "", text).replace("/tankbot/", "")
        worker.logs.append(text, stream="output")
    elif event["op"] == "fault":
        worker.fault = event.get("code", "MODULE_ERROR")
        worker.timing.finish(worker.fault,event.get("location","runtime_bridge"))
        worker.detail = event.get("detail", "")
        worker.close()


def start(sources=None, *, startup_is_deployment=False):
    from tankbot_host.deployment import DeploymentManager
    authority = Authority(load_config("/tankbot/config/m1.json"), startup_sources=sources,
                          core_factory=WasmCore, worker_factory=BrowserSupervisor, startup_is_deployment=startup_is_deployment)
    authority.deployment = DeploymentManager(authority)
    return authority


def diagnostics(authority):
    def dist(values):
        values = sorted(values)
        return {"count":len(values),"p50_ms":values[len(values)//2] if values else None,
                "p95_ms":values[min(len(values)-1,int(len(values)*.95))] if values else None,
                "max_ms":max(values,default=None)}
    return {"tick":authority.tick,"run_id":authority.run_id,"runtime_fault":authority.worker.fault,
            "profile":{"chassis":authority.config["scene"]["default_chassis"],"view_mode":authority.config["view_mode"],
                       "entry_point":authority.contract["entry_point"],"fault":authority.config["module"]["fault"],
                       "control_sources":authority.config["control_sources"]},
            "effective_config_sha256":hashlib.sha256(json.dumps(authority.config,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            "pose_commits":sum(e["event"]=="pose_commit" for e in authority.audit),
            "rejections":[e for e in authority.audit if e["event"]=="rejected"],
            "tick_cost":dist(authority.tick_times_ms),"batch_cost":dist(authority.worker.batch_times_ms),
            "max_view_bytes":authority.max_view_bytes,
            "fixed_commit_gates":all(e["tick"]-e.get("activation_tick",e["sample_tick"])==authority.delay for e in authority.audit if e["event"]=="pose_commit"),
            "shots_fired":authority._sensors.get("/robot/weapons/cannon/state",{}).get("payload",{}).get("shots_fired",0)}
