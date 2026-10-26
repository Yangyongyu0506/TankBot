"""M1 authority: fixed gates, explicit permissions, private core adapter and view projection."""
import copy
import math
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
from .campaign import active as campaign_level, validate_profile, CampaignSession, RadarSimulator, catalog
from .logs import RuntimeLogs

ROOT = Path(__file__).resolve().parents[2]


def core_configuration(config):
    # Level discovery/tutorials belong to Host. Preserve the existing private physics DTO.
    return {key:value for key,value in config.items() if key not in ("campaign","level_plugins","robot_graph")}


def load_config(path):
    from .configuration import load_yaml
    config = load_yaml(path) if Path(path).suffix in (".yaml", ".yml") else strict_loads(Path(path).read_bytes())
    from .chassis_profiles import load_profiles
    load_profiles(config)
    if config.get("level_plugins") and "campaign" not in config:
        from .level_plugins import assemble
        config=assemble(config)
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
    validate_profile(config)
    return config


class CoreAdapter:
    """Trusted native IPC; this object never enters a player or UI context."""
    def __init__(self, config, chassis, binary=None):
        self.limit = config["runtime"]["max_message_bytes"]
        binary = binary or ROOT / "target/debug/core_worker"
        self.binary = str(binary)
        self.build_sha256 = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        self.proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     start_new_session=(os.name == "posix"))
        try:
            self.snapshot = self.call({"op": "init", "config": config, "chassis": chassis})
        except BaseException:
            self.close()
            raise

    def call(self, request):
        if "config" in request:
            request={**request,"config":core_configuration(request["config"])}
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
                 core_factory=CoreAdapter, worker_factory=Supervisor, startup_sources=None, developer_mode=False,
                 startup_is_deployment=None):
        from .chassis_profiles import apply_profiles
        config = apply_profiles(copy.deepcopy(config))
        self.developer_mode = developer_mode
        if config["view_mode"]=="estimated" and (config["view_policy"]["system_pose_allowed"] or config["view_policy"]["world_effects"]):
            raise ValueError("Estimated view cannot grant truth")
        if config["view_mode"]=="weapons-practice" and (not config["view_policy"]["system_pose_allowed"] or not config["view_policy"]["world_effects"]):
            raise ValueError("Practice view requires explicit authority policy")
        validate_wheels(config["wheels"])
        validate_profile(config)
        self.config = copy.deepcopy(config)
        self.graph = None
        self.run_id = uuid.uuid4().hex
        self.controlled = controlled
        self.hz = config["clock"]["physics_hz"]
        self.period = self.hz // config["clock"]["algorithm_hz"]
        self.delay = config["runtime"]["commit_delay_ticks"]
        self.tick = 0
        self.logs = RuntimeLogs(config["runtime"]["max_log_bytes"])
        self.view_revision = 0
        self.validator = Validator(config, self.run_id)
        self.validator.structure(config["view_policy"], "view-policy.schema.json")
        self.selector = PoseSelector("system" if config["view_mode"] in ("weapons-practice", "campaign") and config["view_policy"]["system_pose_allowed"] else config["view"]["pose_source_id"])
        self.gateway = ViewGateway(config["view_policy"])
        self.core = core_factory(config, config["scene"]["default_chassis"], binary)
        self._private = self.core.snapshot
        self._sensors = {}
        self._sampled_tick = None
        self._candidates = {}
        self._target_estimate = None
        self.campaign = CampaignSession(config) if campaign_level(config) else None
        self.radar = RadarSimulator(config) if self.campaign else None
        from .weapon_sensors import GpsInterceptSimulator,ArmorDetectionSimulator
        self.intercepted_gps = GpsInterceptSimulator(config)
        self.armor_detector = ArmorDetectionSimulator(config)
        self._public_pose_history = {}
        self._target_history = {}
        self._sequences = {}
        self._pending = None
        self._last_activation = 0
        self._keyboard = None
        self._turret_target = None
        self._turret_acceleration_target = None
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
        from tankbot._imports import load_policy
        init["import_policy"] = load_policy()
        if config.get("campaign", {}).get("active_level"):
            from .chassis_profiles import target_geometry
            geometry=target_geometry(config)
            from .workspace import starter, read_sources
            init["sources"] = starter(config)
            if workspace is not None:
                init["sources"].update(read_sources(workspace, config["workspace"]))
            init["config"]["lesson"] = {"level_id": config["campaign"]["active_level"],
                                          "transform_tolerance": config["validation"]["numeric_tolerance"],
                                          "processing":self.campaign.definition["runtime"]["processing"]}
            if self.graph_profile() and self.radar.noise is not None:
                noise = self.radar.noise
                init["config"]["observations"] = {"radar_covariance":[[noise["range_stddev_m"]**2,0],[0,noise["bearing_stddev_rad"]**2]]}
            if self.intercepted_gps.sensor:
                variance = self.intercepted_gps.sensor["parameters"]["noise"]["position_stddev_m"]**2
                init["config"]["observations"].update(gps_covariance=[[variance,0],[0,variance]],gps_mount=geometry["gps_mount_m"])
            if self.armor_detector.sensor:
                noise=self.armor_detector.sensor["parameters"]["noise"]
                init["config"]["observations"]={"armor_covariance":[[noise["range_stddev_m"]**2,0],[0,noise["bearing_stddev_rad"]**2]],"armor_mounts":geometry["armor_mounts"]}
            if self.graph_profile():
                import math
                init["config"]["lesson"]["tick_duration_s"] = 1/self.hz
                init["config"]["lesson"]["estimate_history_ticks"] = config["runtime"]["estimate_history_ticks"]
                armor = self.campaign.definition.get("armor_mode",False)
                init["config"]["actuators"] = {"projectile_speed_mps":config["weapons"]["projectile"]["relative_speed_mps"],
                    "max_acceleration_radps2":config["weapons"]["turret"]["acceleration_control"]["max_relative_acceleration_radps2"],
                    "armor_mounts":geometry["armor_mounts"] if armor else [],
                    "enemy_drive_model":self.campaign.definition["target"]["motion"]["chassis"],
                    "enemy_forward_only":self.campaign.definition["target"]["motion"]["forward_speed_mps"] > 0}
        if startup_sources is not None:
            init["sources"] = copy.deepcopy(startup_sources)
        if self.graph_profile():
            from .robot_graph import inspect_graph,bind_publishers,GraphExecution
            from tankbot_protocol.wire import strict_loads
            graph = inspect_graph(init["sources"],strict_loads(init["sources"]["tankbot.json"]),self)
            init["graph"] = bind_publishers(graph,self.run_id)
            self.graph = GraphExecution(self,init["graph"],0)
            self.selector.source_id = "system" if graph["pose_source"]["mode"] == "system" else graph["pose_source"]["module_id"]
        self.worker_factory = worker_factory
        self.worker_init = copy.deepcopy(init)
        self.deployment = None
        try:
            self.worker = worker_factory(config, init)
            self.worker.deployment_id = "startup"
            self.worker.revision = None
            explicit_startup = (workspace is not None or startup_sources is not None) if startup_is_deployment is None else startup_is_deployment
            if self.campaign and explicit_startup and self.campaign.definition["timer_start"] == "first_deployment":
                self.campaign.start(self.tick)
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
        if self.config.get("campaign", {}).get("active_level"):
            runtime_authorized="/robot/localization/pose" in self.runtime_inputs()
            if self.selector.source_id=="system" and (runtime_authorized or self.config["view_policy"]["system_pose_allowed"]):
                pose = SystemPoseProvider.pose(self._private, self.config, runtime_authorized=runtime_authorized)
                candidate = self._message("pose2d@1", "/system/pose", pose, frame="map", publisher="system_pose_provider")
                self.selector.accept("system", candidate, self._message)
                self._sensors["/robot/localization/pose"] = copy.deepcopy(self.selector.canonical)
                self._public_pose_history[self.tick] = copy.deepcopy(pose)
                cutoff = self.tick-self.config["runtime"]["estimate_history_ticks"]
                self._public_pose_history = {tick:value for tick,value in self._public_pose_history.items() if tick>=cutoff}
            radar = self.radar.sample(self._private, self.tick)
            if radar is not None:
                msg = self._message("radar@1", "/robot/sensors/radar", radar, frame="radar_link", publisher="sensor:radar")
                self.validator.validate(msg, now=self.tick, grants={("sensor:radar", msg["channel"], msg["schema"], "radar_link")})
                self._sensors[msg["channel"]] = msg
            gps = self.intercepted_gps.sample(self._private,self.tick)
            if gps is not None:
                msg = self._message("gps_fix@1","/robot/sensors/intercepted_gps",gps,frame="map",publisher="sensor:intercepted_gps")
                self.validator.validate(msg,now=self.tick,grants={("sensor:intercepted_gps",msg["channel"],msg["schema"],"map")})
                self._sensors[msg["channel"]] = msg
            armor=self.armor_detector.sample(self._private,self.tick)
            if armor is not None:
                msg=self._message("armor_detections@1","/robot/sensors/armor_detections",armor,frame="base_link",publisher="sensor:armor_detector")
                self.validator.validate(msg,now=self.tick,grants={("sensor:armor_detector",msg["channel"],msg["schema"],"base_link")})
                self._sensors[msg["channel"]]=msg
        for key, schema, channel in (("joint_states","joint_state@1","/robot/sensors/joint_states"),
                ("imu","imu@1","/robot/sensors/imu"),("turret_joint_states","joint_state@1","/robot/turret/joint_states"),
                ("weapon_state","weapon_state@1","/robot/weapons/cannon/state")):
            if self.campaign and channel not in {sensor["topic"] for sensor in self.campaign.definition["sensors"]}:
                continue
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
        if self.campaign is not None and self.campaign.status != "active":
            raise Rejected("ATTEMPT_ENDED")
        if self.config["control_sources"][actuator] != source or (actuator != "chassis" and not self.config["weapons"]["enabled"]):
            raise Rejected("UNAUTHORIZED")

    def keyboard(self, twist):
        self._require_control("chassis", "keyboard")
        self._rate_limit()
        msg = self._message("twist@1", "/robot/cmd_vel", twist, frame="base_link", publisher="ui")
        self.validator.validate(msg, now=self.tick, grants={("ui", "/robot/cmd_vel", "twist@1", "base_link")})
        self._manual_start(any(twist[part][axis] for part in ("linear", "angular") for axis in ("x", "y", "z")))
        # Controller's single keyboard lease; M1 has no simultaneous algorithm actuator grant.
        self._keyboard = msg

    def turret_keyboard(self, value):
        self._require_control("turret", "keyboard")
        self._rate_limit()
        msg = self._message("turret_velocity@1","/robot/turret/cmd_vel",value,frame="base_link",publisher="ui")
        self.validator.validate(msg,now=self.tick,grants={("ui",msg["channel"],msg["schema"],"base_link")})
        self._manual_start(value["velocity_radps"] != 0)
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
        self._manual_start(True)
        self._sequences["ui","fire"]=msg["sequence_number"]+1
        return self._queue_fire(msg)

    def _manual_start(self, effective):
        if not effective or self.campaign is None or self.campaign.started_tick is not None:
            return
        if self.campaign.definition["timer_start"] != "first_control":
            raise Rejected("DEPLOY_TO_START_ATTEMPT")
        self.campaign.start(self.tick)

    def select_pose_source(self, source_id):
        if self.graph is not None:
            candidates = [mid for mid,m in self.graph.graph["modules"].items() if f"/robot/estimates/{mid}/pose" in m["output_channels"].values()]
            if not self.config["view_policy"]["player_pose_allowed"] or source_id not in candidates:
                raise Rejected("UNAUTHORIZED")
            self.selector.source_id = source_id
            self.graph.graph["pose_source"] = {"mode":"player","module_id":source_id,"fallback":"none"}
            self.selector.canonical = None
            self._sensors.pop("/robot/localization/pose",None)
            candidate = self._candidates.get(source_id)
            if candidate and 0 <= self.tick-candidate["simulation_tick"] <= self.config["view_policy"]["pose_hide_after_ticks"]:
                self.selector.accept(source_id,candidate,self._message)
                self._sensors["/robot/localization/pose"] = copy.deepcopy(self.selector.canonical)
            self.view_revision += 1
            self._build_view()
            return
        if self.config["view_mode"]!="estimated" or source_id != self.contract["module_id"]:
            raise Rejected("UNAUTHORIZED")
        self.config["view"]["pose_source_id"] = source_id
        self.selector.source_id = source_id
        self.selector.canonical = None
        self.view_revision += 1

    def _commit(self):
        if self.graph is not None:
            return self._commit_graph()
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
                if p["results"] == [{"module_id": self.contract["module_id"], "status": "failed", "error_code": "DEPENDENCY_NOT_ALLOWED"}]:
                    raise Rejected("DEPENDENCY_NOT_ALLOWED")
                raise Rejected("MODULE_ERROR")
            if len(p["outputs"]) > len(self.contract["outputs"]):
                raise Rejected("RATE_LIMITED")
            grants = {(self.publisher_id,channel,self.contract["outputs"][port]["schema"],
                       None if port=="fire" else "map" if port in ("pose", "target") else "base_link")
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
                elif msg["schema"] == "target_estimate@1":
                    old = self._target_estimate
                    if old is None or (msg["simulation_tick"], msg["sequence_number"]) > (old["simulation_tick"], old["sequence_number"]):
                        self._target_estimate = copy.deepcopy(msg)
                        if self.campaign is not None:
                            self.campaign.estimate(msg, self._target_history.get(msg["simulation_tick"]))
                        self.audit.append({"event": "target_commit", "tick": self.tick, "sample_tick": msg["simulation_tick"]})
                elif msg["schema"]=="twist@1":
                    self._keyboard=msg
                elif msg["schema"]=="turret_velocity@1":
                    self._turret_target={**msg["payload"],"source_tick":msg["simulation_tick"]}
                elif msg["schema"]=="fire_command@1":
                    self._queue_fire(msg)
            self._failures = 0
        except Rejected as e:
            self.audit.append({"event": "rejected", "tick": self.tick, "code": e.code})
            self.logs.append("Runtime 批次失败：" + e.code + "\n", source="runtime", module_id=self.contract["module_id"], tick=self.tick, stream="error",
                             deployment_id=getattr(self.worker, "deployment_id", "startup"), revision=getattr(self.worker, "revision", None))
            self._failures += 1
            if self._failures >= self.config["runtime"]["max_failures"] or self.worker.fault:
                self._faulted = True
                self._revoke_robot = True
                self.worker.close()

    def _activate(self):
        if self.graph is not None:
            return self._activate_graph()
        if self.tick == 0 or self.tick % self.period or self._faulted or (self.campaign is not None and self.campaign.status != "active"):
            return
        inputs = []
        for port, binding in self.contract["inputs"].items():
            channel=self.input_channels[port]
            msg = self._sensors.get(channel) if self.campaign is None or channel in self.runtime_inputs() else None
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
        campaign = bool(self.config.get("campaign", {}).get("active_level"))
        if not self._private.get("player_alive", True):
            self.selector.canonical = None
            self._sensors.clear()
        else:
            if self.config["view_mode"] in ("campaign","weapons-practice") and (self.config["view_policy"]["world_effects"] or self.config["view_policy"]["true_enemy_objects"]):
                practice=SystemPoseProvider.project(self._private,self.config,self.tick)
            if self.selector.source_id=="system" and self.config["view_policy"]["system_pose_allowed"]:
                pose=SystemPoseProvider.pose(self._private,self.config)
                system=self._message("pose2d@1","/system/pose",pose,frame="map",publisher="system_pose_provider")
                self.selector.accept("system",system,self._message)
        payload = self.gateway.build(self.tick,self.view_revision,self.selector,self._sensors,practice=practice,
                                     target_estimate=self._target_estimate, campaign=campaign)
        schema = "view_snapshot@4" if self.graph is not None and campaign else "view_snapshot@3" if campaign else "view_snapshot@2" if practice is not None else "view_snapshot@1"
        self.view = self._message(schema, "/view/snapshot", payload, frame=None, publisher="view_gateway")
        self.validator.structure(self.view)
        import json
        self.max_view_bytes = max(self.max_view_bytes, len(json.dumps(self.view).encode()))

    def graph_profile(self):
        level = self.config.get("campaign",{}).get("active_level")
        name = self.config["campaign"]["levels"][level].get("robot_profile") if level else None
        return self.config.get("robot_graph",{}).get("profiles",{}).get(name) if name else None

    def runtime_inputs(self):
        return self.campaign.definition["permissions"]["data_access"]["inputs"] if self.campaign else self.input_channels.values()

    def graph_inputs(self):
        if self.campaign:
            return self.campaign.definition["permissions"]["data_access"]["inputs"]
        profile = self.graph_profile()
        if profile is not None:
            return profile["grants"]["inputs"]
        from .module_profile import module_profile
        contract, inputs, _ = module_profile(self.config)
        return {channel:contract["inputs"][port]["schema"] for port,channel in inputs.items()
                if channel != "/robot/sensors/radar" or (self.campaign and "sensor.radar.read" in self.campaign.definition["capabilities"])}

    def graph_outputs(self):
        if self.campaign:
            grants=self.campaign.definition["permissions"]["data_access"]
            return {**{schema:None for schema in grants["outputs"]},**grants["actuators"]}
        profile = self.graph_profile()
        if profile is not None:
            return {**{name:None for name in profile["grants"]["outputs"]},**profile["grants"]["actuators"]}
        from .module_profile import module_profile
        contract, _, outputs = module_profile(self.config)
        result = {p["schema"]:None for p in contract["outputs"].values()}
        result.update({channel:contract["outputs"][port]["schema"] for port,channel in outputs.items() if channel in (
            "/robot/cmd_vel","/robot/turret/cmd_vel","/robot/weapons/cannon/fire")})
        return result

    def _activate_graph(self):
        if self._pending is not None or self._faulted or (self.campaign and self.campaign.status != "active"):
            return
        request = self.graph.request(self.tick)
        if request is not None and self.worker.submit(request):
            self.graph.submitted(request)
            self._pending = {"step_id":request["request_id"],"activation":self.tick,"commit":self.tick+self.delay,"request":request}
            self.audit.append({"event":"activation","tick":self.tick,"commit_tick":self.tick+self.delay,
                               "modules":[m["module_id"] for m in request["payload"]["modules"]]})

    def _commit_graph(self):
        if self._pending is None or self.tick != self._pending["commit"]:
            return
        pending,self._pending = self._pending,None
        response = self.worker.finish(controlled=self.controlled)
        try:
            if response is None:
                raise Rejected(self.worker.fault or "MISSED_DEADLINE")
            self.graph.commit(self.graph.check(response,pending["request"],self.validator))
        except Rejected as error:
            self.audit.append({"event":"rejected","tick":self.tick,"code":error.code})
            self.logs.append("Robot Runtime: "+error.code+"\n",source="runtime",module_id=self.contract["module_id"],tick=self.tick,stream="error")
            self._faulted = True
            self._revoke_robot = True
            self.worker.close()

    def accept_graph_output(self, module_id, message, *, activation_tick):
        channel, schema = message["channel"],message["schema"]
        if channel == f"/robot/estimates/{module_id}/pose":
            self._candidates[module_id] = copy.deepcopy(message)
            self.selector.accept(module_id,message,self._message)
            if self.selector.source_id == module_id:
                self._sensors["/robot/localization/pose"] = copy.deepcopy(self.selector.canonical)
            self.audit.append({"event":"pose_commit","module_id":module_id,"tick":self.tick,"sample_tick":message["simulation_tick"],"activation_tick":activation_tick})
        elif channel in (f"/robot/estimates/{module_id}/target",f"/robot/estimates/{module_id}/target_pose",f"/robot/estimates/{module_id}/target_polar"):
            profile = self.graph_profile()
            if profile is None or module_id == profile.get("target_source"):
                if schema=="target_polar_estimate@1":
                    message = self._project_polar_estimate(message)
                    if message is None:
                        return
                old = self._target_estimate
                if old is None or message["simulation_tick"] >= old["simulation_tick"]:
                    self._target_estimate = copy.deepcopy(message)
                    if self.campaign:
                        self.campaign.estimate(message,self._target_history.get(message["simulation_tick"]))
        elif channel == "/robot/cmd_vel":
            self._keyboard = copy.deepcopy(message)
        elif channel == "/robot/turret/cmd_vel":
            self._turret_target = {**message["payload"],"source_tick":message["simulation_tick"]}
        elif channel == "/robot/turret/cmd_accel":
            self._turret_acceleration_target = {**message["payload"],"source_tick":message["simulation_tick"]}
        elif channel == "/robot/weapons/cannon/fire":
            self._queue_fire(message)

    def _project_polar_estimate(self, message):
        """Display/evaluation projection using the same published self-pose the player may read."""
        pose = self._public_pose_history.get(message["simulation_tick"])
        if pose is None:
            return None
        p = message["payload"]
        angle = pose["yaw_rad"]+p["bearing_rad"]
        c,s,r = math.cos(angle),math.sin(angle),p["range_m"]
        covariance = p["covariance"]
        if covariance is not None:
            jacobian = [[c,-r*s],[s,r*c]]
            covariance = [sum(jacobian[i][a]*covariance[2*a+b]*jacobian[j][b] for a in range(2) for b in range(2)) for i in range(2) for j in range(2)]
        return self._message("target_estimate@1","/view/target_estimate",{"x_m":pose["x_m"]+r*c,"y_m":pose["y_m"]+r*s,"covariance":covariance},
                             frame="map",publisher="view_gateway",tick=message["simulation_tick"])

    def advance(self):
        """Process boundary n, then advance to S_(n+1). Player computation is never awaited in real time."""
        started = time.monotonic()
        self.collect_logs(self.worker, "runtime")
        if self.campaign is not None:
            alive = [target for target in self._private["targets"] if target["alive"]]
            self._target_history[self.tick] = alive[0]["pose"] if alive else None
            cutoff = self.tick-self.config["runtime"]["estimate_history_ticks"]
            self._target_history = {tick: pose for tick, pose in self._target_history.items() if tick >= cutoff}
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
        if self._turret_acceleration_target is not None:
            command["turret_acceleration_target"] = self._turret_acceleration_target
        if self.config["control_sources"]["chassis"] == "disabled":
            command.update(target=None,revoke=True)
        if self.campaign is not None and self.campaign.status != "active":
            command.update(target=None, turret_target=None, fire_requests=[], revoke=True, revoke_turret=True)
            command.pop("turret_acceleration_target",None)
        self.replay.append({"tick": self.tick, "target": target, "actuators":copy.deepcopy(command), "truth_pose": self._private["truth_pose"],
                            "truth_velocity": self._private["truth_velocity"]})
        self._private = self.core.call(command)
        self._turret_target=None
        self._turret_acceleration_target=None
        self._fire_pending=[]
        self._revoke_robot=False
        for publisher,result in self._private["fire_results"]:
            self._fire_journal[publisher,result["request_id"]]=result
        self.tick += 1
        if self.campaign is not None:
            outcome = self.campaign.outcome(self._private, self.tick)
            if outcome:
                self._finish_campaign(passed=self.campaign.outcome_passed(outcome), reason=outcome)
        self.tick_times_ms.append((time.monotonic()-started)*1000)

    def collect_logs(self, worker, source):
        incoming = getattr(worker, "logs", None)
        if incoming is None:
            return
        batch = incoming.drain()
        for item in batch["entries"]:
            self.logs.append(item["text"], source=source, module_id=self.contract["module_id"],
                             tick=self.tick, stream=item.get("stream", "output"),
                             deployment_id=getattr(worker, "deployment_id", "startup"), revision=getattr(worker, "revision", None))
        if batch["dropped"]:
            self.logs.append("[输出过多，部分日志已省略]\n", source=source, module_id=self.contract["module_id"], tick=self.tick, stream="notice")

    def _finish_campaign(self, *, passed=False, reason="aborted"):
        if self.campaign is None:
            raise Rejected("NO_ACTIVE_LEVEL")
        if self.campaign.status == "active":
            self.campaign.finish(self.tick, passed=passed, reason=reason)
            self._pending = None
            self._keyboard = self._turret_target = None
            self._turret_acceleration_target = None
            self._fire_pending.clear()
            self.worker.close()
            self.collect_logs(self.worker, "runtime")
            if self.deployment is not None:
                self.deployment.close()
            self._target_estimate = None
            self.view_revision += 1
            self._build_view()
        return self.campaign_status()

    def finish_campaign(self):
        return self._finish_campaign()

    def campaign_status(self):
        return {"run_id": self.run_id, "attempt": self.campaign.public() if self.campaign is not None else None}

    def developer_snapshot(self):
        """Explicit developer grant; never included in PlayerViewSnapshot or Runtime inputs."""
        if not self.developer_mode:
            raise Rejected("UNAUTHORIZED")
        target_visuals = {}
        from .chassis_profiles import target_geometry
        for target in self.config["weapons"]["targets"]:
            motion = target.get("motion")
            if motion is None:
                continue
            chassis = motion["chassis"]
            target_visuals[target["target_id"]] = {
                **target_geometry(self.config,target),
                "chassis_visual": copy.deepcopy(self.config["rendering"]["chassis_models"][chassis]),
                "wheel_calibration": public_calibration(self.config["wheels"]) if chassis == "omnidirectional" else None,
            }
        return {"version": 1, "run_id": self.run_id, "simulation_tick": self.tick,
                "truth": copy.deepcopy(self._private), "sensors": copy.deepcopy(self._sensors),
                "target_visuals": target_visuals,
                "pose_candidates": copy.deepcopy(self._candidates),
                "selected_pose": copy.deepcopy(self.selector.canonical),
                "target_estimate": copy.deepcopy(self._target_estimate),
                "audit": copy.deepcopy(list(self.audit)[-100:]),
                "runtime": {"module_id": self.contract["module_id"], "fault": self.worker.fault,
                            "control_sources": copy.deepcopy(self.config["control_sources"])}}

    def public_profile(self):
        from .chassis_profiles import target_geometry
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
                "campaign": {"active_level": campaign_level(self.config), "levels": catalog(self.config),"chapters":copy.deepcopy(self.config.get("campaign",{}).get("chapters",[]))},
                "radar_calibration": ({key: copy.deepcopy(self.config["campaign"]["radar"][key])
                                       for key in ("range_m", "field_of_view_rad", "update_hz", "mount_m", "yaw_rad", "frame_id")}
                                      if self.campaign is not None and self.campaign.definition["radar_profile"] else None),
                "armor_calibration":({"range_m":self.armor_detector.sensor["parameters"]["range_m"],"update_hz":self.armor_detector.sensor["update_hz"],"frame_id":"base_link"} if self.armor_detector.sensor else None),
                "control_sources":copy.deepcopy(self.config["control_sources"]),
                "turret_muzzle_offset_m":copy.deepcopy(self.config["weapons"]["turret"]["muzzle_offset_m"]),
                "projectile_radius_m": self.config["weapons"]["projectile"]["radius_m"],
                "armor_width_m":self.campaign.definition["target"].get("armor",{}).get("width_m") if self.campaign else None,
                "target_geometry":target_geometry(self.config),
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
