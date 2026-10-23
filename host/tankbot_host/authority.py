"""M1 authority: fixed gates, explicit permissions, private core adapter and view projection."""
import copy
from collections import deque
import hashlib
import os
from pathlib import Path
import subprocess
import time
import uuid
from tankbot_protocol.validation import Validator, Rejected, envelope
from tankbot_protocol.wire import send, receive, strict_loads
from .supervisor import Supervisor
from .view import PoseSelector, ViewGateway, SystemPoseProvider
from .wheel_geometry import validate_wheels, public_calibration

ROOT = Path(__file__).resolve().parents[2]


def load_config(path):
    config = strict_loads(Path(path).read_bytes())
    Validator(config, "configuration").structure(config, "simulation-profile.schema.json")
    if config["confirmation_status"] != "confirmed":
        raise ValueError("Physical profile not confirmed")
    # No defaults: all runtime and controller fields must be present.
    required = {
        "runtime": ("commit_delay_ticks", "batch_budget_ms", "startup_timeout_s", "max_message_bytes", "max_failures", "input_max_age_ticks", "max_log_bytes", "seed"),
        "view": ("pose_source_id", "snapshot_hz", "max_visual_trail", "poll_ms", "keyboard_refresh_ms", "keyboard_linear_mps", "keyboard_yaw_radps"),
        "host": ("bind", "port", "max_catchup_ticks"),
        "module": ("module_id", "entry_point", "pose_offset_m", "output_frame", "fault"),
        "sensors": ("imu_mount", "imu_axes", "planar_gravity_mps2", "noise_stddev", "bias", "drift_per_s", "latency_ticks", "drop_probability", "encoder_model"),
    }
    for section, names in required.items():
        for name in names:
            config[section][name]
    s = config["sensors"]
    if s["imu_mount"] != "center_of_mass" or s["imu_axes"] != "base_link" or s["encoder_model"] != "ideal_rolling" or any(s[k] != 0 for k in ("planar_gravity_mps2", "noise_stddev", "bias", "drift_per_s", "latency_ticks", "drop_probability")):
        raise ValueError("M1 implements only the confirmed ideal sensor profile")
    hz = config["clock"]["physics_hz"]
    period = hz // config["clock"]["algorithm_hz"]
    if hz % config["clock"]["algorithm_hz"] or period < config["runtime"]["commit_delay_ticks"]:
        raise ValueError("Unsupported algorithm schedule")
    if hz % config["view"]["snapshot_hz"]:
        raise ValueError("View frequency must divide physics frequency")
    if config["view_policy"]["pose_fresh_ticks"] > config["view_policy"]["pose_hide_after_ticks"]:
        raise ValueError("Invalid pose age limits")
    rendering = config["rendering"]
    if rendering["history_ms"] <= max(rendering["interpolation_delay_ms"], rendering["estimate_interpolation_delay_ms"]) + 1000/config["view"]["snapshot_hz"]:
        raise ValueError("Render history must cover interpolation delay and a snapshot interval")
    validate_wheels(config["wheels"])
    return config


class CoreAdapter:
    """Trusted native IPC; this object never enters a player or UI context."""
    def __init__(self, config, chassis, binary=None):
        self.limit = config["runtime"]["max_message_bytes"]
        binary = binary or ROOT / "target/debug/core_worker"
        self.build_sha256 = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        self.proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     start_new_session=(os.name == "posix"))
        try:
            self.snapshot = self.call({"op": "init", "config": config, "chassis": chassis})
        except BaseException:
            self.close()
            raise

    def call(self, request):
        send(self.proc.stdin, request, self.limit)
        response = receive(self.proc.stdout, self.limit)
        if not response["ok"]:
            raise ValueError(response["error"])
        self.snapshot = response["data"]
        return self.snapshot

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.proc.stdin.close()
        self.proc.stdout.close()


class Authority:
    def __init__(self, config, *, workspace=None, binary=None, controlled=False,
                 core_factory=CoreAdapter, worker_factory=Supervisor):
        if config["view_mode"]=="estimated" and (config["view_policy"]["system_pose_allowed"] or config["view_policy"]["world_effects"]):
            raise ValueError("Estimated view cannot grant truth")
        if config["view_mode"]=="weapons-practice" and (not config["view_policy"]["system_pose_allowed"] or not config["view_policy"]["world_effects"]):
            raise ValueError("Practice view requires explicit authority policy")
        validate_wheels(config["wheels"])
        self.config = copy.deepcopy(config)
        self.run_id = uuid.uuid4().hex
        self.controlled = controlled
        self.hz = config["clock"]["physics_hz"]
        self.period = self.hz // config["clock"]["algorithm_hz"]
        self.delay = config["runtime"]["commit_delay_ticks"]
        self.tick = 0
        self.view_revision = 0
        self.validator = Validator(config, self.run_id)
        self.validator.structure(config["view_policy"], "view-policy.schema.json")
        self.selector = PoseSelector("system" if config["view_mode"]=="weapons-practice" else config["view"]["pose_source_id"])
        self.gateway = ViewGateway(config["view_policy"])
        self.core = core_factory(config, config["scene"]["default_chassis"], binary)
        self._private = self.core.snapshot
        self._sensors = {}
        self._sampled_tick = None
        self._candidates = {}
        self._sequences = {}
        self._pending = None
        self._last_activation = 0
        self._keyboard = None
        self._turret_target = None
        self._fire_pending = []
        self._fire_journal = {}
        self._revoke_robot = False
        self._command_ticks = deque()
        self._command_wall_times = deque()
        self._failures = 0
        self._faulted = False
        self.audit = deque(maxlen=config["runtime"]["audit_limit_entries"])
        self.replay = deque(maxlen=config["runtime"]["history_limit_ticks"])  # Private evaluator data; no HTTP endpoint.
        self.tick_times_ms = deque(maxlen=config["runtime"]["history_limit_ticks"])
        self.max_view_bytes = 0
        self._sample()
        from .module_profile import module_profile
        self.contract, self.input_channels, self.output_channels = module_profile(config)
        self.publisher_id = "module:" + self.contract["module_id"]
        self.validator.structure(self.contract, "module-contract.schema.json")
        if not config["scene"]["public_initial_pose"]:
            self.core.close()
            raise ValueError("M1 example requires a task-authorized initial pose")
        init = {"workspace": str(Path(workspace or ROOT / "examples/robot").resolve()), "config": {
            "initial_pose": config["scene"]["initial_pose"], "wheels": config["wheels"], "module": config["module"]},
            "contract": self.contract, "physics_hz": self.hz, "run_id": self.run_id,
            "publisher_id": self.publisher_id, "input_channels": self.input_channels, "output_channels": self.output_channels}
        self.worker_factory = worker_factory
        self.worker_init = copy.deepcopy(init)
        self.deployment = None
        try:
            self.worker = worker_factory(config, init)
        except BaseException:
            self.core.close()
            raise
        self._build_view()

    def _message(self, schema, channel, payload, *, frame, publisher="authority", tick=None):
        seq = self._sequences.get((publisher, channel), 0)
        self._sequences[publisher, channel] = seq+1
        return envelope(schema, channel, payload, tick=self.tick if tick is None else tick, hz=self.hz,
                        run_id=self.run_id, publisher_id=publisher, sequence=seq, frame_id=frame)

    def _sample(self):
        if self._sampled_tick == self.tick:
            return
        values = self._private["sensors"]
        if values is None:
            return
        self._sampled_tick = self.tick
        for key, schema, channel in (("joint_states","joint_state@1","/robot/sensors/joint_states"),
                ("imu","imu@1","/robot/sensors/imu"),("turret_joint_states","joint_state@1","/robot/turret/joint_states"),
                ("weapon_state","weapon_state@1","/robot/weapons/cannon/state")):
            if key not in values:
                continue
            msg = self._message(schema, channel, values[key], frame="base_link")
            self.validator.validate(msg, now=self.tick, grants={("authority", channel, schema, "base_link")})
            self._sensors[channel] = msg

    def _rate_limit(self):
        now = time.monotonic()
        while self._command_ticks and self._command_ticks[0] <= self.tick-self.hz:
            self._command_ticks.popleft()
        while self._command_wall_times and self._command_wall_times[0] <= now-1:
            self._command_wall_times.popleft()
        if len(self._command_ticks) >= self.config["runtime"]["max_cmd_vel_per_sim_second"] or len(self._command_wall_times) >= self.config["runtime"]["max_inbound_per_wall_second"]:
            raise Rejected("RATE_LIMITED")
        self._command_ticks.append(self.tick)
        self._command_wall_times.append(now)
    def _require_control(self, actuator, source):
        if self.config["control_sources"][actuator] != source or (actuator != "chassis" and not self.config["weapons"]["enabled"]):
            raise Rejected("UNAUTHORIZED")

    def keyboard(self, twist):
        self._require_control("chassis", "keyboard")
        self._rate_limit()
        msg = self._message("twist@1", "/robot/cmd_vel", twist, frame="base_link", publisher="ui")
        self.validator.validate(msg, now=self.tick, grants={("ui", "/robot/cmd_vel", "twist@1", "base_link")})
        # Controller's single keyboard lease; M1 has no simultaneous algorithm actuator grant.
        self._keyboard = msg

    def turret_keyboard(self, value):
        self._require_control("turret", "keyboard")
        self._rate_limit()
        msg = self._message("turret_velocity@1","/robot/turret/cmd_vel",value,frame="base_link",publisher="ui")
        self.validator.validate(msg,now=self.tick,grants={("ui",msg["channel"],msg["schema"],"base_link")})
        self._turret_target = {**msg["payload"],"source_tick":self.tick}

    def _queue_fire(self, msg):
        key = (msg["publisher_id"],msg["request_id"])
        if key in self._fire_journal:
            return copy.deepcopy(self._fire_journal[key])
        limits=self.config["weapons"]["firing"]
        if len(self._fire_journal)>=limits["request_cache_capacity"] or len(self._fire_pending)>=limits["pending_capacity"]:
            raise Rejected("RESOURCE_LIMIT")
        self._fire_pending.append({"publisher_id":msg["publisher_id"],"request_id":msg["request_id"],"source_tick":msg["simulation_tick"]})
        receipt={"request_id":msg["request_id"],"status":"queued"}
        self._fire_journal[key]=receipt
        return copy.deepcopy(receipt)

    def fire_keyboard(self, value):
        self._require_control("weapon","keyboard")
        self._rate_limit()
        if not isinstance(value,dict) or set(value)!={"request_id"}:
            raise Rejected("INVALID_SCHEMA")
        msg=envelope("fire_command@1","/robot/weapons/cannon/fire",{},tick=self.tick,hz=self.hz,
                     run_id=self.run_id,publisher_id="ui",sequence=self._sequences.get(("ui","fire"),0),
                     message_type="command",request_id=value["request_id"])
        self.validator.validate(msg,now=self.tick,grants={("ui",msg["channel"],msg["schema"],None)})
        self._sequences["ui","fire"]=msg["sequence_number"]+1
        return self._queue_fire(msg)

    def select_pose_source(self, source_id):
        if self.config["view_mode"]!="estimated" or source_id != self.contract["module_id"]:
            raise Rejected("UNAUTHORIZED")
        self.config["view"]["pose_source_id"] = source_id
        self.selector.source_id = source_id
        self.selector.canonical = None
        self.view_revision += 1

    def _commit(self):
        if self._pending is None or self._pending["commit"] != self.tick:
            return
        pending, self._pending = self._pending, None
        response = self.worker.finish(controlled=self.controlled)
        try:
            if response is None:
                raise Rejected(self.worker.fault or "MISSED_DEADLINE")
            self.validator.validate(response, now=self.tick,
                                    grants={("runtime", "/runtime/step", "runtime_step_result@1", None)},
                                    source_tick=pending["activation"])
            p = response["payload"]
            expected_result = [{"module_id": self.contract["module_id"], "status": "completed", "error_code": None}]
            if response["schema"] != "runtime_step_result@1" or response["channel"] != "/runtime/step" or response["message_type"] != "service_response" or response["publisher_id"] != "runtime" or response["frame_id"] is not None or response["run_id"] != self.run_id or response["request_id"] != pending["step_id"] or p["step_id"] != pending["step_id"]:
                raise Rejected("UNAUTHORIZED")
            if response["simulation_tick"] != pending["activation"] or response["simulation_time_ns"] != pending["activation"]*1_000_000_000//self.hz:
                raise Rejected("INVALID_TIMESTAMP")
            if p["results"] != expected_result:
                raise Rejected("MODULE_ERROR")
            if len(p["outputs"]) > len(self.contract["outputs"]):
                raise Rejected("RATE_LIMITED")
            grants = {(self.publisher_id,channel,self.contract["outputs"][port]["schema"],
                       None if port=="fire" else "map" if port=="pose" else "base_link")
                      for port,channel in self.output_channels.items()}
            seen=set()
            for msg in p["outputs"]:
                if msg["channel"] in seen:
                    raise Rejected("RATE_LIMITED")
                seen.add(msg["channel"])
                self.validator.validate(msg,now=self.tick,grants=grants,source_tick=pending["activation"],consume=False)
                if msg["schema"]=="fire_command@1" and (msg["publisher_id"],msg["request_id"]) not in self._fire_journal:
                    limits=self.config["weapons"]["firing"]
                    if len(self._fire_journal)>=limits["request_cache_capacity"] or len(self._fire_pending)>=limits["pending_capacity"]:
                        raise Rejected("RESOURCE_LIMIT")
            for msg in p["outputs"]:
                self.validator.validate(msg,now=self.tick,grants=grants,source_tick=pending["activation"])
                if msg["schema"]=="pose2d@1":
                    old=self._candidates.get(self.contract["module_id"])
                    if old is None or (msg["simulation_tick"],msg["sequence_number"])>(old["simulation_tick"],old["sequence_number"]):
                        self._candidates[self.contract["module_id"]]=msg
                        self.selector.accept(self.contract["module_id"],msg,self._message)
                    self.audit.append({"event":"pose_commit","tick":self.tick,"sample_tick":msg["simulation_tick"]})
                elif msg["schema"]=="twist@1":
                    self._keyboard=msg
                elif msg["schema"]=="turret_velocity@1":
                    self._turret_target={**msg["payload"],"source_tick":msg["simulation_tick"]}
                elif msg["schema"]=="fire_command@1":
                    self._queue_fire(msg)
            self._failures = 0
        except Rejected as e:
            self.audit.append({"event": "rejected", "tick": self.tick, "code": e.code})
            self._failures += 1
            if self._failures >= self.config["runtime"]["max_failures"] or self.worker.fault:
                self._faulted = True
                self._revoke_robot = True
                self.worker.close()

    def _activate(self):
        if self.tick == 0 or self.tick % self.period or self._faulted:
            return
        inputs = []
        for port, binding in self.contract["inputs"].items():
            msg = self._sensors.get(self.input_channels[port])
            if msg is None or self.tick-msg["simulation_tick"] > binding["max_age_ticks"]:
                if binding["required"]:
                    self.audit.append({"event": "skipped", "tick": self.tick, "code": "INPUT_UNAVAILABLE"})
                    return
            else:
                inputs.append(copy.deepcopy(msg))
        step_id = f"step-{self.tick}"
        payload = {"step_id": step_id, "activation_tick": self.tick, "output_commit_tick": self.tick+self.delay,
                   "modules": [{"module_id": self.contract["module_id"], "dt_ticks": self.tick-self._last_activation}], "inputs": inputs}
        request = envelope("runtime_step_request@1", "/runtime/step", payload, tick=self.tick, hz=self.hz,
                           run_id=self.run_id, publisher_id="supervisor", sequence=self.tick,
                           message_type="service_request", request_id=step_id)
        self.validator.structure(request)
        if self.worker.submit(request):
            self._pending = {"step_id": step_id, "activation": self.tick, "commit": self.tick+self.delay}
            self._last_activation = self.tick
            self.audit.append({"event": "activation", "tick": self.tick, "commit_tick": self.tick+self.delay})

    def _build_view(self):
        practice = None
        if self.config["view_mode"]=="weapons-practice":
            practice=SystemPoseProvider.project(self._private,self.config,self.tick)
            system=self._message("pose2d@1","/system/pose",practice["pose"],frame="map",publisher="system_pose_provider")
            self.selector.accept("system",system,self._message)
        payload = self.gateway.build(self.tick,self.view_revision,self.selector,self._sensors,practice=practice)
        self.view = self._message("view_snapshot@2" if practice is not None else "view_snapshot@1", "/view/snapshot", payload, frame=None, publisher="view_gateway")
        self.validator.structure(self.view)
        import json
        self.max_view_bytes = max(self.max_view_bytes, len(json.dumps(self.view).encode()))

    def advance(self):
        """Process boundary n, then advance to S_(n+1). Player computation is never awaited in real time."""
        started = time.monotonic()
        if self.deployment is not None:
            self.deployment.advance()
        self._commit()
        self._sample()
        self._activate()
        if self.tick % (self.hz // self.config["view"]["snapshot_hz"]) == 0:
            self._build_view()
        target = None
        if self._keyboard:
            p = self._keyboard["payload"]
            target = {"vx": p["linear"]["x"], "vy": p["linear"]["y"], "wz": p["angular"]["z"], "source_tick": self._keyboard["simulation_tick"]}
            self._keyboard = None
        command={"op":"step","target":target,"turret_target":self._turret_target,"fire_requests":self._fire_pending,
                 "revoke":self._revoke_robot and self.config["control_sources"]["chassis"]=="robot",
                 "revoke_turret":self._revoke_robot and self.config["control_sources"]["turret"]=="robot"}
        self.replay.append({"tick": self.tick, "target": target, "actuators":copy.deepcopy(command), "truth_pose": self._private["truth_pose"],
                            "truth_velocity": self._private["truth_velocity"]})
        self._private = self.core.call(command)
        self._turret_target=None
        self._fire_pending=[]
        self._revoke_robot=False
        for publisher,result in self._private["fire_results"]:
            self._fire_journal[publisher,result["request_id"]]=result
        self.tick += 1
        self.tick_times_ms.append((time.monotonic()-started)*1000)

    def public_profile(self):
        limits = copy.deepcopy(self.config["motion_limits"])
        chassis = self.config["scene"]["default_chassis"]
        if not self.config["chassis"][chassis]["lateral_actuation"]:
            limits["max_vy_mps"] = 0.0
        controller = {"controller_profile_version":"1.0", "controller_id":"base_controller", "drive_model":chassis,
                      "command_topic":"/robot/cmd_vel", "command_frame":"base_link",
                      "cmd_vel_timeout":self.config["controller"]["cmd_vel_timeout_s"], "limits":limits}
        self.validator.structure(controller, "chassis-controller.schema.json")
        calibration=public_calibration(self.config["wheels"]) if chassis=="omnidirectional" else None
        if calibration is not None:
            self.validator.structure(calibration,"wheel-calibration.schema.json")
        return {"run_id": self.run_id, "physics_hz": self.hz, "chassis": self.config["scene"]["default_chassis"],
                "controller_profile":controller,"view_mode":self.config["view_mode"],
                "control_sources":copy.deepcopy(self.config["control_sources"]),
                "turret_muzzle_offset_m":copy.deepcopy(self.config["weapons"]["turret"]["muzzle_offset_m"]),
                "body": {k: self.config["body"][k] for k in ("length_m", "width_m", "corner_radius_m")},
                "walls": copy.deepcopy(self.config["scene"]["walls"]) if self.config["scene"]["public_map"] and self.config["view_policy"]["public_map"] else [],
                "view": copy.deepcopy(self.config["view"]),
                "rendering": {k:copy.deepcopy(v) for k,v in self.config["rendering"].items() if k != "chassis_models"},
                "wheel_calibration":calibration,
                "chassis_visual":copy.deepcopy(self.config["rendering"]["chassis_models"][chassis])}

    def truth_digest(self):
        import json
        return hashlib.sha256(json.dumps(list(self.replay), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def close(self):
        if self.deployment is not None:
            self.deployment.close()
        self.worker.close()
        self.core.close()
