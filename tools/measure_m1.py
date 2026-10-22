#!/usr/bin/env python3
"""Private evaluator report for the 600-tick M1 profile; never served to the browser."""
import copy
from datetime import date
import hashlib
import json
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"host"),str(ROOT/"protocol"),str(ROOT/"sdk/python")]
from tankbot_host.authority import Authority, CoreAdapter, load_config


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    values = sorted(values)
    return {"p50_ms": statistics.median(values), "p95_ms": values[int((len(values)-1)*.95)], "max_ms": max(values)} if values else None


def measure(config):
    start = time.monotonic()
    authority = Authority(config, controlled=True)
    cold_ms = (time.monotonic()-start)*1000
    max_error, sensor_samples = 0.0, 0
    try:
        for tick in range(config["validation"]["ticks"]):
            if tick % authority.period == 0:
                v = config["validation"]["probe_target"]
                vy = v[0] if config["scene"]["default_chassis"]=="omnidirectional" else v[1]
                authority.keyboard({"linear":{"x":v[0],"y":vy,"z":0},"angular":{"x":0,"y":0,"z":v[2]}})
            authority.advance()
            sensor_samples += authority._private["sensors"] is not None
            selected = authority.view["payload"]["selected_pose"]
            if selected:
                true_pose = authority.replay[selected["simulation_tick"]]["truth_pose"]
                p = selected["pose"]
                max_error = max(max_error, ((p["x_m"]-true_pose[0])**2+(p["y_m"]-true_pose[1])**2)**.5)
        core = CoreAdapter(config, config["scene"]["default_chassis"])
        exact = True
        try:
            for record in authority.replay:
                exact &= core.snapshot["truth_pose"] == record["truth_pose"] and core.snapshot["truth_velocity"] == record["truth_velocity"]
                core.call({"op":"step","target":record["target"]})
        finally:
            core.close()
        return {"chassis":config["scene"]["default_chassis"], "ticks":authority.tick,
                "cold_start_ms":cold_ms, "host_tick_including_ipc_and_validation":distribution(authority.tick_times_ms),
                "worker_round_trip":distribution(authority.worker.batch_times_ms), "max_view_bytes":authority.max_view_bytes,
                "sensor_sampling_ticks":sensor_samples,"pose_commits":sum(e["event"]=="pose_commit" for e in authority.audit),
                "rejections":[e for e in authority.audit if e["event"]=="rejected"], "max_estimate_position_error_m":max_error,
                "same_build_replay_exact":bool(exact), "truth_digest":authority.truth_digest()}
    finally:
        authority.close()


def main():
    config = load_config(ROOT/"config/m1.json")
    report = {"date":date.today().isoformat(), "os":platform.platform(), "python":platform.python_version(),
              "cpu":next((line.split(":",1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),platform.processor()) if sys.platform=="linux" else platform.processor(),
              "native_binary_sha256":digest(ROOT/"target/debug/core_worker"), "cargo_lock_sha256":digest(ROOT/"Cargo.lock"),
              "config_sha256":digest(ROOT/"config/m1.json"), "scene":{"dynamic_bodies":1+int(config["weapons"]["enabled"]),"static_walls":len(config["scene"]["walls"])}, "runs":[]}
    for name in config["chassis"]:
        candidate = copy.deepcopy(config);candidate["scene"]["default_chassis"] = name
        report["runs"].append(measure(candidate))
    start = time.monotonic()
    wasm = json.loads(subprocess.check_output(["node",str(ROOT/"tools/wasm_probe.mjs")],cwd=ROOT))
    wasm["cold_instantiate_and_run_ms"] = (time.monotonic()-start)*1000
    wasm["sha256"] = digest(ROOT/"target/wasm32-unknown-unknown/debug/tankbot_core.wasm")
    native = json.loads(subprocess.check_output([sys.executable,str(ROOT/"tools/tankbot.py"),"probe"],cwd=ROOT))
    report["wasm_probe"] = wasm
    report["native_probe_x_m"] = native
    report["native_wasm_probe_equal"] = native==wasm["final_x_m"]
    if not report["native_wasm_probe_equal"] or any(not r["same_build_replay_exact"] or r["rejections"] or r["max_estimate_position_error_m"]>config["validation"]["odom_error_tolerance_m"] for r in report["runs"]):
        raise SystemExit("M1 measurement acceptance failed")
    path = ROOT/"docs/reports/m1-current-profile.json"  # Preserve the historical M1 evidence.
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(path.relative_to(ROOT))


if __name__=="__main__":
    main()
