"""Shared asynchronous Edit/Test/Deploy lifecycle, driven only at Authority tick boundaries."""
import ast
import copy
import hashlib
from pathlib import Path
import sys
import uuid
from tankbot_protocol.validation import Validator, Rejected, envelope
from tankbot_protocol.wire import strict_loads
from .workspace import digest, validate_files, artifact_files, ROOT
from tankbot._imports import load_policy, validate_imports


def environment(config, core_sha256, runtime_packages=None):
    paths = list((ROOT / "docs/schemas").glob("*.json"))
    paths += list((ROOT / "sdk/python").rglob("*.py"))
    paths += list((ROOT / "runtime").glob("*.py"))
    paths += list((ROOT / "host/tankbot_host").glob("*.py"))
    paths += list((ROOT / "protocol/tankbot_protocol").glob("*.py"))
    paths += [ROOT / "requirements.txt", ROOT / "config/browser-assets.lock.json", ROOT / "config/player-dependencies.yaml", ROOT / "config/game.yaml"]
    return digest({"config": config, "core_sha256": core_sha256, "python": sys.version, "platform": sys.platform,
                   "runtime_packages": runtime_packages or {},
                   "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}})


def inspect_snapshot(snapshot, authority):
    files = snapshot["files"]
    validate_files(files, authority.config["workspace"])
    revision = snapshot["revision"]
    if revision != digest({"files": files, "ledger": snapshot["ledger"]}):
        raise ValueError("SNAPSHOT_DIGEST_MISMATCH")
    reserved = set(sys.stdlib_module_names) | {"tankbot", "tankbot_protocol", "module_runner", "source_loader", "js", "pyodide", "numpy"}
    for path, source in files.items():
        if path.endswith(".py") and path.split("/")[0].split(".")[0] in reserved:
            raise ValueError("RESERVED_MODULE: " + path)
        if path.endswith(".py"):
            try:
                ast.parse(source, filename=path)
            except SyntaxError as error:
                raise ValueError(f"{path}:{error.lineno}:{error.offset}: {error.msg}") from error
    from .campaign_templates import framework_upgrade
    upgrade = framework_upgrade(authority.config, files)
    if upgrade["required"]:
        raise ValueError("TEACHING_TEMPLATE_UPGRADE_REQUIRED: " + upgrade["message"])
    validate_imports(files, load_policy())
    manifest = strict_loads(files["tankbot.json"])
    validator = authority.validator
    validator.structure(manifest, "workspace.schema.json")
    if manifest["sdk_version"] != "0.1.0" or manifest["dependencies"] or len(manifest["modules"]) != 1:
        raise ValueError("UNSUPPORTED_WORKSPACE_PROFILE: 当前仅开放一个模块、NumPy、SDK 与指定基础标准库，不支持自行安装外部依赖。")
    module = manifest["modules"][0]
    contract = strict_loads(files[module["contract"]])
    validator.structure(contract, "module-contract.schema.json")
    expected = copy.deepcopy(authority.contract)
    expected["entry_point"] = contract["entry_point"]
    expected["state_version"] = contract["state_version"]
    if contract != expected or module["module_id"] != contract["module_id"] or manifest["entry_point"] != contract["entry_point"]:
        raise ValueError("CONTRACT_PROFILE_MISMATCH")
    mid = contract["module_id"]
    connections = [{"from": channel, "to": f"{mid}.{port}"} for port, channel in authority.input_channels.items()]
    connections += [{"from": f"{mid}.{port}", "to": channel} for port, channel in authority.output_channels.items()]
    if sorted(manifest["connections"], key=digest) != sorted(connections, key=digest):
        raise ValueError("UNAUTHORIZED_CONNECTION")
    expected_source = ({"mode": "system", "module_id": None, "fallback": "none"}
                       if authority.config.get("campaign", {}).get("active_level") else
                       {"mode": "player", "module_id": mid, "fallback": "none"})
    if manifest["pose_source"] != expected_source:
        raise ValueError("UNAUTHORIZED_POSE_SOURCE")
    packaged = artifact_files(files)
    env = environment(authority.config, authority.core.build_sha256, (authority.worker.startup_result or {}).get("runtime_packages", {}))
    sha = digest({"files": {p: hashlib.sha256(s.encode()).hexdigest() for p, s in packaged.items()}, "environment": env})
    return {"sha256": sha, "revision": revision, "environment": env, "files": packaged,
            "test_files": copy.deepcopy(files), "contract": contract, "module_config": module["config"]}


class DeploymentManager:
    def __init__(self, authority):
        self.authority = authority
        self.job = None
        self.artifacts = {}
        self.reports = {}
        self.active = None
        self.history = []
        self.last = None

    def status(self):
        self.authority.collect_logs(self.authority.worker, "runtime")
        if self.job:
            self.authority.collect_logs(self.job["worker"], self.job["kind"])
        return copy.deepcopy({"active": self.active, "history": self.history,
                              "job": None if self.job is None else {k: self.job[k] for k in ("id", "kind", "phase", "sha256")},
                              "last": self.last, "reports": list(self.reports.values()),
                              "run_id": self.authority.run_id, "tick": self.authority.tick,
                              "attempt_status": self.authority.campaign.status if self.authority.campaign else None,
                              "runtime_fault": self.authority.worker.fault or ("MODULE_ERROR" if self.authority._faulted else None),
                              "logs": self.authority.logs.public()})

    def start(self, kind, snapshot=None, sha256=None):
        if self.authority.campaign is not None and self.authority.campaign.status != "active":
            raise ValueError("ATTEMPT_ENDED: 请先重试或开始下一关")
        if self.job is not None:
            raise ValueError("DEPLOYMENT_BUSY")
        a = self.authority
        if kind in ("test", "deploy"):
            try:
                artifact = inspect_snapshot(snapshot, a)
            except (ValueError, SyntaxError) as error:
                a.logs.append(str(error) + "\n", source=kind, module_id=a.contract["module_id"], tick=a.tick, stream="error")
                raise
        elif kind == "rollback" and sha256 in self.artifacts:
            artifact = copy.deepcopy(self.artifacts[sha256])
        else:
            raise ValueError("INVALID_DEPLOYMENT_REQUEST")
        sha = artifact["sha256"]
        if len(self.artifacts) >= a.config["workspace"]["max_deployments"] and sha not in self.artifacts:
            raise ValueError("DEPLOYMENT_LIMIT: export your project and restart the session")
        if kind != "test":
            report = self.reports.get(sha)
            if not report or report["revision"] != artifact["revision"] or report["environment"] != environment(a.config, a.core.build_sha256, (a.worker.startup_result or {}).get("runtime_packages", {})):
                raise ValueError("TEST_REQUIRED_FOR_THIS_SNAPSHOT_AND_PROFILE")
        init = copy.deepcopy(a.worker_init)
        init["contract"] = copy.deepcopy(artifact["contract"])
        init["config"]["module"] = {**init["config"]["module"], **artifact["module_config"]}
        init["publisher_id"] = "module:" + a.contract["module_id"] + ":" + uuid.uuid4().hex
        init["sources"] = artifact["test_files"] if kind == "test" else artifact["files"]
        init["test_mode"] = kind == "test"
        init["start_tick"] = a.tick
        init["reset_reason"] = "deployment"
        worker = a.worker_factory(a.config, init, deferred=True)
        job_id = uuid.uuid4().hex
        worker.deployment_id = job_id
        worker.revision = artifact["revision"]
        self.job = {"id": job_id, "kind": kind, "phase": "Starting", "sha256": sha,
                    "artifact": artifact, "worker": worker, "init": init, "count": 0, "pending": None,
                    "validator": Validator(a.config, a.run_id)}
        self.last = None
        return self.status()

    def _fail(self, error):
        job = self.job
        job["worker"].close()
        self.authority.collect_logs(job["worker"], job["kind"])
        self.authority.logs.append(str(error) + "\n", source=job["kind"], module_id=self.authority.contract["module_id"], tick=self.authority.tick, stream="error", deployment_id=job["id"], revision=job["artifact"]["revision"])
        self.last = {"id": job["id"], "kind": job["kind"], "sha256": job["sha256"], "revision": job["artifact"]["revision"], "status": "Failed", "error": str(error)}
        self.job = None

    def _check(self, response, job, tick):
        a, v = self.authority, job["validator"]
        v.validate(response, now=a.tick, source_tick=tick, grants={("runtime", "/runtime/step", "runtime_step_result@1", None)})
        p = response["payload"]
        if response["request_id"] != f"check-{tick}" or p["step_id"] != f"check-{tick}" or response["simulation_tick"] != tick:
            raise ValueError("INVALID_TEST_RESPONSE")
        if p["results"] != [{"module_id": a.contract["module_id"], "status": "completed", "error_code": None}]:
            if p["results"] == [{"module_id": a.contract["module_id"], "status": "failed", "error_code": "DEPENDENCY_NOT_ALLOWED"}]:
                raise ValueError("DEPENDENCY_NOT_ALLOWED: 当前仅开放 NumPy、SDK 和指定基础标准库，请查看关卡说明。")
            raise ValueError("MODULE_ERROR")
        grants = {(job["init"]["publisher_id"], ch, a.contract["outputs"][port]["schema"], None if port == "fire" else "map" if port in ("pose", "target") else "base_link") for port, ch in a.output_channels.items()}
        seen = set()
        for msg in p["outputs"]:
            if msg["channel"] in seen:
                raise ValueError("DUPLICATE_OUTPUT")
            seen.add(msg["channel"])
            v.validate(msg, now=a.tick, source_tick=tick, grants=grants)

    def advance(self):
        if self.job is None:
            return
        a, job = self.authority, self.job
        worker = job["worker"]
        a.collect_logs(worker, job["kind"])
        try:
            if not worker.poll_ready():
                if worker.fault:
                    raise ValueError(worker.fault + (": " + worker.detail if worker.detail else ""))
                return
            if worker.fault:
                raise ValueError(worker.fault + (": " + worker.detail if worker.detail else ""))
            if job["kind"] != "test":
                if a.tick % a.period == 0:
                    self._activate(job)
                return
            job["phase"] = "Testing"
            pending = job["pending"]
            if pending is not None and a.tick >= pending + a.delay:
                response = worker.finish(controlled=a.controlled)
                if response is None:
                    raise ValueError(worker.fault or "MISSED_DEADLINE")
                self._check(response, job, pending)
                job["count"] += 1
                job["pending"] = None
                if job["count"] >= a.config["workspace"]["test_batches"]:
                    artifact = job["artifact"]
                    report = {"status": "Ready", "sha256": artifact["sha256"], "revision": artifact["revision"],
                              "environment": artifact["environment"], "unit_tests": (worker.startup_result or {}).get("unit_tests", 0),
                              "simulation_batches": job["count"], "max_batch_ms": max(worker.batch_times_ms, default=0),
                              "checks": ["paths", "syntax", "manifest", "contract", "unit_tests", "authorized_sensor_simulation", "output_permissions", "runtime_budget"]}
                    self.artifacts[artifact["sha256"]] = artifact
                    self.reports[artifact["sha256"]] = report
                    self.last = {**report, "kind": "test", "id": job["id"]}
                    worker.close()
                    self.job = None
                    return
            if job["pending"] is None and a.tick % a.period == 0:
                # Observe the live authorized sensor stream; test outputs never reach actuators or the view.
                a._sample()
                tick = a.tick
                request = envelope("runtime_step_request@1", "/runtime/step",
                    {"step_id": f"check-{tick}", "activation_tick": tick, "output_commit_tick": tick + a.delay,
                     "modules": [{"module_id": a.contract["module_id"], "dt_ticks": a.period}],
                     "inputs": [copy.deepcopy(a._sensors[channel]) for channel in a.input_channels.values() if channel in a._sensors]}, tick=tick, hz=a.hz, run_id=a.run_id,
                    publisher_id="supervisor", sequence=tick, message_type="service_request", request_id=f"check-{tick}")
                if not worker.submit(request):
                    raise ValueError("TEST_SUBMIT_FAILED")
                job["pending"] = tick
        except (ValueError, RuntimeError, KeyError, TypeError) as error:
            self._fail(error)

    def _activate(self, job):
        a = self.authority
        old, old_publisher = a.worker, a.publisher_id
        a.worker = job["worker"]
        a.publisher_id = job["init"]["publisher_id"]
        a.contract = copy.deepcopy(job["artifact"]["contract"])
        a._pending = None
        a._last_activation = a.tick - a.period
        a._failures, a._faulted = 0, False
        a._revoke_robot = True
        if a.config["control_sources"]["chassis"] == "robot":
            a._keyboard = None
        if a.config["control_sources"]["turret"] == "robot":
            a._turret_target = None
        a._fire_pending = [f for f in a._fire_pending if f["publisher_id"] != old_publisher]
        a._candidates.clear()
        a._target_estimate = None
        a.selector.canonical = None
        a.view_revision += 1
        for table in (a.validator.sequences, a.validator.target_ticks):
            for key in list(table):
                if key[0] in ("runtime", old_publisher):
                    del table[key]
        self.active = {"deployment_id": job["id"], "sha256": job["sha256"], "revision": job["artifact"]["revision"], "activated_tick": a.tick}
        if a.campaign is not None and a.campaign.definition["timer_start"] == "first_deployment":
            a.campaign.start(a.tick)
        self.history.append(copy.deepcopy(self.active))
        self.history = self.history[-a.config["workspace"]["max_deployments"]:]
        a.audit.append({"event": "deployment_activated", "tick": a.tick, **self.active})
        self.last = {**self.active, "id": job["id"], "status": "Active", "kind": job["kind"]}
        self.job = None
        old.close()
        a.collect_logs(old, "runtime")

    def close(self):
        if self.job:
            self.job["worker"].close()
            self.job = None
