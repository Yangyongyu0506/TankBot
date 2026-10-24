"""Shared multi-file module lifecycle for native CPython and Pyodide. No Core dependency."""
import contextlib
import importlib
import sys
import traceback
from importlib.metadata import PackageNotFoundError, version
from dataclasses import asdict
from tankbot import Module, ModuleContext, Inputs, Sample, Pose2D, RadarData, ImuData, JointState, WeaponState, FireCommand
from tankbot_protocol.message import envelope
from tankbot._imports import DependencyNotAllowed


def runtime_packages() -> dict[str, str]:
    try:
        return {"numpy": version("numpy")}
    except PackageNotFoundError:
        return {}

class ModuleRunner:
    def __init__(self, init):
        sys.path.insert(0, init["workspace"])
        self.init = init
        self.sequence = 0
        config = init["config"]
        self.contract = contract = init["contract"]
        start_tick = init.get("start_tick", 0)
        context = ModuleContext(start_tick, 0.0, start_tick, config)
        with contextlib.redirect_stdout(sys.stderr):
            path, name = contract["entry_point"].split(":")
            self.module = module = getattr(importlib.import_module(path), name)()
            if not isinstance(module, Module):
                raise TypeError("Entry point must implement Module")
            module.setup(context)
            module.reset(context, init.get("reset_reason", "new_run"))

    def step(self, request):
        init, contract, config = self.init, self.contract, self.init["config"]
        converters = {"imu@1": ImuData, "radar@1": RadarData, "pose2d@1": Pose2D,
                      "joint_state@1": lambda **p: JointState(**{k: tuple(v) for k, v in p.items()}), "weapon_state@1": WeaponState}
        p = request["payload"]
        tick = p["activation_tick"]
        context = ModuleContext(tick, p["modules"][0]["dt_ticks"] / init["physics_hz"], p["output_commit_tick"], config)
        samples = {}
        for port, channel in init["input_channels"].items():
            candidates = [m for m in p["inputs"] if m["channel"] == channel]
            if candidates:
                m = max(candidates, key=lambda x: (x["simulation_tick"], x["sequence_number"]))
                samples[port] = Sample(converters[m["schema"]](**m["payload"]), m["simulation_tick"], m["frame_id"], m["sequence_number"])
        outputs = []
        try:
            with contextlib.redirect_stdout(sys.stderr):
                self.module.update(Inputs(samples), context)
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
        result = {"step_id": p["step_id"], "results": [{"module_id": contract["module_id"], "status": status, "error_code": error}], "outputs": outputs}
        response = envelope("runtime_step_result@1", "/runtime/step", result, tick=tick,
                            hz=init["physics_hz"], run_id=init["run_id"], publisher_id="runtime",
                            sequence=self.sequence, message_type="service_response", request_id=p["step_id"])
        self.sequence += 1
        self.context = context
        return response

    def close(self):
        with contextlib.redirect_stdout(sys.stderr):
            self.module.teardown(getattr(self, "context", ModuleContext(0, 0.0, 0, self.init["config"])))
