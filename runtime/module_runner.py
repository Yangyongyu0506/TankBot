"""Shared multi-file module lifecycle for native CPython and Pyodide. No Core dependency."""
import contextlib
import importlib
import sys
import traceback
import time
from tankbot.messages import decode_message
from tankbot.diagnostics import diagnostic_scope
from importlib.metadata import PackageNotFoundError, version
from dataclasses import asdict
from tankbot import Module, ModuleContext, Inputs, Sample, Pose2D, RadarData, ArmorDetections, ImuData, JointState, WeaponState, FireCommand, TargetEstimate, TargetPoseEstimate, TargetPoints, GpsFixData, PositionFix2D, WaypointGoal, PolarTargetEstimate, Twist, Vector3, TurretAcceleration, TurretVelocity
from tankbot_protocol.message import envelope
from tankbot._imports import DependencyNotAllowed


def runtime_packages() -> dict[str, str]:
    try:
        return {"numpy": version("numpy")}
    except PackageNotFoundError:
        return {}

class ModuleRunner:
    def __new__(cls, init):
        if "graph" in init:
            from graph_runner import GraphRunner
            return GraphRunner(init)
        return super().__new__(cls)

    def __init__(self, init):
        sys.path.insert(0, init["workspace"])
        self.init = init
        self.sequence = 0
        config = init["config"]
        if "experiment_seed" in init:
            import random
            import numpy as np
            random.seed(init["experiment_seed"]);np.random.seed(init["experiment_seed"])
        self.contract = contract = init["contract"]
        start_tick = init.get("start_tick", 0)
        context = ModuleContext(start_tick, 0.0, start_tick, config)
        with contextlib.redirect_stdout(sys.stderr):
            path, name = contract["entry_point"].split(":")
            self.module = module = getattr(importlib.import_module(path), name)()
            if not isinstance(module, Module):
                raise TypeError("Entry point must implement Module")
            import inspect
            if any(inspect.iscoroutinefunction(getattr(module, name)) for name in ("setup","reset","update","teardown")):
                raise TypeError("Module lifecycle must be synchronous")
            module.setup(context)
            if not init.get("defer_reset",False):
                module.reset(context, init.get("reset_reason", "new_run"))

    def step(self, request):
        decode_started = time.perf_counter()
        init, contract, config = self.init, self.contract, self.init["config"]
        p = request["payload"]
        tick = p["activation_tick"]
        context = ModuleContext(tick, p["modules"][0]["dt_ticks"] / init["physics_hz"], p["output_commit_tick"], config)
        samples = {}
        for port, channel in init["input_channels"].items():
            candidates = [m for m in p["inputs"] if m["channel"] == channel]
            if candidates:
                m = max(candidates, key=lambda x: (x["simulation_tick"], x["sequence_number"]))
                samples[port] = Sample(decode_message(m["schema"], m["payload"]), m["simulation_tick"], m["frame_id"], m["sequence_number"])
        outputs = []
        update_started = time.perf_counter()
        update_finished = update_started
        try:
            with contextlib.redirect_stdout(sys.stderr), diagnostic_scope(context):
                self.module.update(Inputs(samples), context)
            update_finished = time.perf_counter()
            for port, schema, payload, frame, sample_tick in context._outputs:
                if port not in init["output_channels"] or contract["outputs"][port]["schema"] != schema:
                    raise ValueError("Undeclared output port/type")
                outputs.append(envelope(schema, init["output_channels"][port], payload, tick=sample_tick,
                                        hz=init["physics_hz"], run_id=init["run_id"], publisher_id=init["publisher_id"],
                                        sequence=self.sequence, frame_id=frame))
                self.sequence += 1
            for port, request_id in context._commands:
                if port not in init["output_channels"] or contract["outputs"][port]["schema"] != "fire_command@1":
                    raise ValueError("Undeclared fire port")
                outputs.append(envelope("fire_command@1", init["output_channels"][port], asdict(FireCommand()), tick=tick,
                                        hz=init["physics_hz"], run_id=init["run_id"], publisher_id=init["publisher_id"],
                                        sequence=self.sequence, message_type="command", request_id=request_id))
                self.sequence += 1
            status, error = "completed", None
        except DependencyNotAllowed:
            traceback.print_exc(file=sys.stderr)
            outputs = []
            status, error = "failed", "DEPENDENCY_NOT_ALLOWED"
        except Exception:
            traceback.print_exc(file=sys.stderr)
            outputs = []
            status, error = "failed", "MODULE_ERROR"
        finished = time.perf_counter()
        if update_finished == update_started:update_finished = finished
        telemetry = {"modules": [{"module_id": contract["module_id"], "input_decode_ms": (update_started-decode_started)*1000,
                                  "update_ms": (update_finished-update_started)*1000, "output_build_ms": (finished-update_finished)*1000}],
                     "diagnostics": [{"module_id": contract["module_id"], **item} for item in context._diagnostics]}
        result = {"telemetry": telemetry, "step_id": p["step_id"], "results": [{"module_id": contract["module_id"], "status": status, "error_code": error}], "outputs": outputs}
        response = envelope("runtime_step_result@1", "/runtime/step", result, tick=tick,
                            hz=init["physics_hz"], run_id=init["run_id"], publisher_id="runtime",
                            sequence=self.sequence, message_type="service_response", request_id=p["step_id"])
        self.sequence += 1
        self.context = context
        return response

    def close(self):
        with contextlib.redirect_stdout(sys.stderr):
            self.module.teardown(getattr(self, "context", ModuleContext(0, 0.0, 0, self.init["config"])))
