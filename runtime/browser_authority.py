"""Trusted Pyodide adapters. Loaded ONLY in the Core Worker, never in the robot bundle."""
from collections import deque
import json
import hashlib
import time
from tankbot_protocol.wire import strict_loads
from tankbot_host.authority import Authority, load_config


class WasmCore:
    def __init__(self, config, chassis, binary=None):
        self.snapshot = self.call({"op":"init", "config":config, "chassis":chassis})

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
    def __init__(self, config, init):
        self.limit = config["runtime"]["max_message_bytes"]
        self.budget = config["runtime"]["batch_budget_ms"]/1000
        self.batch_times_ms = deque(maxlen=config["runtime"]["history_limit_ticks"])
        self.fault = None
        self.active = self.result = None
        self.closed = False
        self.send("init", {"init":init,"limit":self.limit,"budget_ms":self.budget*1000,
                           "probe":config["browser"]["probe_enabled"],
                           "startup_timeout_s":config["browser"]["startup_timeout_s"]})

    def send(self, op, value):
        from js import runtime_send
        runtime_send(json.dumps({"op":op,"value":value}, allow_nan=False))

    def submit(self, request):
        if self.closed or self.fault or self.active:
            return False
        self.active = request["request_id"]
        self.started = time.monotonic()
        self.result = None
        self.send("step", request)
        return True

    def receive(self, raw, elapsed_ms):
        try:
            if self.closed or self.active is None or self.result is not None:
                raise ValueError("Unsolicited runtime output")
            if elapsed_ms > self.budget*1000 or time.monotonic()-self.started > self.budget:
                raise ValueError("Deadline")
            if not isinstance(raw,str) or len(raw.encode()) > self.limit:
                raise ValueError("Size")
            self.result = strict_loads(raw)
            self.batch_times_ms.append(elapsed_ms)
        except (ValueError, TypeError, RecursionError):
            self.fault = "RESOURCE_LIMIT"
            self.close()

    def finish(self, *, controlled=False):
        # Never wait on this Worker. The browser event loop delivers results between ticks.
        result = self.result
        self.active = self.result = None
        if self.fault or result is None:
            self.fault = self.fault or "MISSED_DEADLINE"
            self.close()
            return None
        return result

    def close(self):
        if not self.closed:
            self.closed = True
            self.send("close", {})


def start():
    return Authority(load_config("/tankbot/config/m1.json"), workspace="/workspace",
                     core_factory=WasmCore, worker_factory=BrowserSupervisor)


def diagnostics(authority):
    def dist(values):
        values = sorted(values)
        return {"count":len(values),"p50_ms":values[len(values)//2] if values else None,
                "p95_ms":values[min(len(values)-1,int(len(values)*.95))] if values else None,
                "max_ms":max(values,default=None)}
    return {"tick":authority.tick,"run_id":authority.run_id,"runtime_fault":authority.worker.fault,
            "profile":{"chassis":authority.config["scene"]["default_chassis"],"view_mode":authority.config["view_mode"],
                       "entry_point":authority.config["module"]["entry_point"],"fault":authority.config["module"]["fault"],
                       "control_sources":authority.config["control_sources"]},
            "effective_config_sha256":hashlib.sha256(json.dumps(authority.config,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            "pose_commits":sum(e["event"]=="pose_commit" for e in authority.audit),
            "rejections":[e for e in authority.audit if e["event"]=="rejected"],
            "tick_cost":dist(authority.tick_times_ms),"batch_cost":dist(authority.worker.batch_times_ms),
            "max_view_bytes":authority.max_view_bytes,
            "fixed_commit_gates":all(e["tick"]-e["sample_tick"]==authority.delay for e in authority.audit if e["event"]=="pose_commit"),
            "shots_fired":authority._sensors.get("/robot/weapons/cannon/state",{}).get("payload",{}).get("shots_fired",0)}
