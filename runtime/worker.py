"""External trusted-local CPython worker; this process is NOT an OS security sandbox."""
import contextlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "sdk/python"), str(ROOT / "protocol")]
from tankbot import Module, ModuleContext, Inputs, Sample, ImuData, JointState
from tankbot_protocol.wire import receive, send
from tankbot_protocol.validation import envelope


def main():
    limit = int(sys.argv[1])
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    init = receive(source, limit)
    # No World, private profile, map seed or core pipe in this initialization object.
    sys.path.insert(0, init["workspace"])
    config = init["config"]
    contract = init["contract"]
    context = ModuleContext(0, 0.0, 0, config)
    with contextlib.redirect_stdout(sys.stderr):
        path, name = contract["entry_point"].split(":")
        module = getattr(importlib.import_module(path), name)()
        if not isinstance(module, Module):
            raise TypeError("Entry point must implement Module")
        module.setup(context)
        module.reset(context, "new_run")
    send(sink, {"ready": True}, limit)
    sequence = 0
    converters = {"imu@1": ImuData, "joint_state@1": lambda **p: JointState(**{k: tuple(v) for k, v in p.items()})}
    try:
        while True:
            request = receive(source, limit)
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
                    module.update(Inputs(samples), context)
                for port, schema, payload, frame, sample_tick in context._outputs:
                    if port not in init["output_channels"] or contract["outputs"][port]["schema"] != schema:
                        raise ValueError("Undeclared output port/type")
                    outputs.append(envelope(schema, init["output_channels"][port], payload, tick=sample_tick,
                                            hz=init["physics_hz"], run_id=init["run_id"], publisher_id=init["publisher_id"],
                                            sequence=sequence, frame_id=frame))
                    sequence += 1
                status, error = "completed", None
            except Exception:
                outputs = []
                status, error = "failed", "MODULE_ERROR"
            result = {"step_id": p["step_id"], "results": [{"module_id": contract["module_id"], "status": status, "error_code": error}], "outputs": outputs}
            response = envelope("runtime_step_result@1", "/runtime/step", result, tick=tick,
                                hz=init["physics_hz"], run_id=init["run_id"], publisher_id="runtime",
                                sequence=sequence, message_type="service_response", request_id=p["step_id"])
            sequence += 1
            send(sink, response, limit)
    except EOFError:
        with contextlib.redirect_stdout(sys.stderr):
            module.teardown(context)


if __name__ == "__main__":
    main()
