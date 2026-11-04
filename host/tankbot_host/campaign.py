"""Trusted lesson configuration, sensor simulation and end-of-attempt evaluation."""
import copy
import math
import random
import importlib.util


def active(config):
    return config.get("campaign", {}).get("active_level")


def ensure_native_numpy() -> None:
    if importlib.util.find_spec("numpy") is None:
        raise ValueError("教学 Runtime 缺少 NumPy；请使用 python3 tools/tankbot.py 启动，启动器会自动准备 Python 依赖。")


def validate_profile(config):
    if "campaign" not in config:
        return
    c=config["campaign"]
    if config["view_mode"]=="campaign" and not active(config):
        raise ValueError("Campaign mode requires an active level")
    if set(c["levels"])-c["lessons"].keys():
        raise ValueError("Every level requires a learning guide")
    chapters=c["chapters"]
    members=[lid for chapter in chapters for lid in chapter["levels"]]
    if len(members)!=len(c["levels"]) or set(members)!=set(c["levels"]):
        raise ValueError("Chapters must contain every level exactly once")
    for lid,level in c["levels"].items():
        if type(level["time_limit_s"]) is not int or level["time_limit_s"]<=0:
            raise ValueError("Each level requires a positive time_limit_s")
        if level["armor_mode"]!=bool((level["target"] or {}).get("armor")):
            raise ValueError("Armor lesson and physical target disagree")
        name=level.get("robot_profile")
        if name and name not in config["robot_graph"]["profiles"]:
            raise ValueError("Unknown robot graph profile")
        if name:
            from .level_plugins import ACTUATORS
            for channel in config["robot_graph"]["profiles"][name]["grants"]["actuators"]:
                if channel not in ACTUATORS or level["control_sources"][ACTUATORS[channel][1]]!="robot":
                    raise ValueError("Actuator graph grant and lesson control disagree")


def configure(config, level_id):
    """Compile one already validated plugin into the existing simulation/runtime adapters."""
    if level_id not in config.get("campaign",{}).get("levels",{}):
        raise ValueError("UNKNOWN_LEVEL")
    c=copy.deepcopy(config)
    campaign=c["campaign"];campaign["active_level"]=level_id
    level=campaign["levels"][level_id]
    c["view_mode"]="campaign"
    c["module"].update(**level["runtime"]["logical_module"],fault="none")
    c["module"]["weapon_demo"]["enabled"]=False
    c["control_sources"]=copy.deepcopy(level["control_sources"])
    c["clock"]=copy.deepcopy(level["world_simulation"])
    c["solver"]["dt"]=1/(c["clock"]["physics_hz"]*c["clock"]["substeps"])
    c["scene"].update(copy.deepcopy(level["scene"]))
    c["weapons"]["enabled"]=level.get("weapons_enabled",True)
    c["weapons"]["targets"]=[copy.deepcopy(level["target"])] if level["target"] else []
    c.pop("wheel_drive",None)
    if level.get("drive")=="wheel_voltage":
        c["wheel_drive"]=copy.deepcopy(c["chassis_profiles"]["differential"]["motor"])
    c["view_policy"]=copy.deepcopy(level["permissions"]["visualization"]["view_policy"])
    c["view"]["pose_source_id"]="system" if level["runtime"]["manifest"]["pose_source"]["mode"]=="system" else level["runtime"]["manifest"]["pose_source"]["module_id"]
    c["runtime"]["seed"]=level["randomization"]["seed"]
    campaign["outcome_priority"]=[o["reason"] for o in level["rules"]["outcomes"]]
    # Compatibility DTO for existing diagnostics/tools; the active noise is a direct component parameter.
    radar=copy.deepcopy(level["radar"])
    if radar:
        profiles=copy.deepcopy(campaign.get("radar",{}).get("profiles",{}))
        profiles[level["radar_profile"]]=radar["noise"]
        campaign["radar"]={**radar,"profiles":profiles}
    else:
        campaign["radar"]={}
    from .chassis_profiles import apply_profiles
    apply_profiles(c,dynamics=True)
    from .maps import apply_override
    apply_override(c)
    validate_profile(c)
    return c


def catalog(config):
    result = []
    for key, value in config.get("campaign", {}).get("levels", {}).items():
        item = {"level_id": key, **{name: copy.deepcopy(value[name]) for name in ("title", "problem", "hints", "capabilities", "objective", "time_limit_s", "timer_start")},
                "chapter_id":value.get("chapter_id"),"control_sources":copy.deepcopy(value.get("control_sources")),"armor_mode":value.get("armor_mode",False),"ui":copy.deepcopy(value["tutorial"]["lesson"]["ui"]),"visualization":copy.deepcopy(value["visualization"]),"allowed_layers":copy.deepcopy(value["permissions"]["visualization"]["allowed_layers"])}
        item.update(prerequisites=copy.deepcopy(value["metadata"]["prerequisites"]),
                    order=value["metadata"]["order"],description=value["metadata"]["description"])
        item["problem"] = item["problem"].format(time_limit_s=value["time_limit_s"], max_hp=(value["target"] or {}).get("health", {}).get("max_hp"))
        feedback=value["evaluation"].get("live_feedback")
        entries=feedback if isinstance(feedback,list) else [feedback] if feedback else []
        allowed=value["permissions"]["visualization"].get("allowed_metrics",[])
        permitted=[copy.deepcopy(entry) for entry in entries if entry["metric"] in allowed]
        for entry in permitted:
            if entry.get("reference_metric") not in allowed:
                for field in ("reference_metric","reference_label","reference_color"):entry.pop(field,None)
        if permitted:item["live_feedback"]=copy.deepcopy(permitted if isinstance(feedback,list) else permitted[0])
        result.append(item)
    return result


def blocked(origin, target, walls):
    """Closed segment/AABB intersection; grazing a wall blocks the point return."""
    delta = [target[i]-origin[i] for i in range(2)]
    for wall in walls:
        lo, hi = 0.0, 1.0
        for axis in range(2):
            minimum = wall["center"][axis]-wall["size"][axis]/2
            maximum = wall["center"][axis]+wall["size"][axis]/2
            if delta[axis] == 0:
                if not minimum <= origin[axis] <= maximum:
                    lo, hi = 1.0, 0.0
                    break
            else:
                a, b = sorted(((minimum-origin[axis])/delta[axis], (maximum-origin[axis])/delta[axis]))
                lo, hi = max(lo, a), min(hi, b)
        if lo <= hi:
            return True
    return False


class RadarSimulator:
    def __init__(self, config):
        self.config = config
        self.settings = config["campaign"]["radar"]
        profile = config["campaign"]["levels"][active(config)]["radar_profile"]
        self.noise = self.settings["noise"] if profile else None
        self.random = random.Random(config["runtime"]["seed"])
        self.last_tick = None

    def sample(self, private, tick):
        if self.noise is None or self.last_tick == tick or tick % (self.config["clock"]["physics_hz"]//self.settings["update_hz"]):
            return None
        self.last_tick = tick
        return self.measure(private,tick)

    def measure(self,private,tick):
        x, y, yaw = private["truth_pose"]
        detections = []
        for target in sorted(private["targets"], key=lambda item: item["target_id"]):
            if not target["alive"]:
                continue
            tx, ty, _ = target["pose"]
            distance = math.hypot(tx-x, ty-y)
            bearing = (math.atan2(ty-y, tx-x)-yaw+math.pi) % math.tau-math.pi
            if distance > self.settings["range_m"] or abs(bearing) > self.settings["field_of_view_rad"]/2 or blocked((x,y), (tx,ty), self.config["scene"]["walls"]):
                continue
            if self.random.random() < self.noise["drop_probability"]:
                continue
            measured_range = max(0.0, distance+self.random.gauss(0, self.noise["range_stddev_m"]))
            measured_bearing = (bearing+self.random.gauss(0, self.noise["bearing_stddev_rad"])+math.pi) % math.tau-math.pi
            detections.append({"observation_id": f"obs-{tick}-{len(detections)}", "range_m": measured_range, "bearing_rad": measured_bearing})
        return {"detections": detections}


class CampaignSession:
    def __init__(self, config):
        self.config = config
        self.level_id = active(config)
        self.definition = config["campaign"]["levels"][self.level_id]
        self.status = "active"
        self.result = None
        self.moved = self.turned = False
        self.hits = 0
        self.hp = (self.definition["target"] or {}).get("health", {}).get("max_hp")
        self.estimates = 0
        self.last_estimate_tick = -1
        self.squared_error = 0.0
        self.error_count = 0
        self.yaw_squared_error = 0.0
        self.yaw_error_count = 0
        from .level_rules import Diagnostics
        self.diagnostics = Diagnostics(self.definition["evaluation"])
        self.reference_diagnostics = Diagnostics(self.definition["evaluation"])
        self.reference_last_tick = -1
        self.started_tick = None
        self.elapsed_ticks = 0
        self.limit_ticks = self.definition["time_limit_s"] * config["clock"]["physics_hz"]
        self.player_max_hp = config["scene"].get("player_health", {}).get("max_hp") if config["scene"].get("player_health") else None
        self.player_hp = self.player_max_hp
        self.deployment_armed = False
        self.controller_faulted = False
        self.path_origin_m = 0.0
        self.path_length_m = 0.0
        self.origin_distance_m = 0.0
        self.sequence = self.definition["rules"].get("command_sequence")
        self.sequence_ticks = self.sequence["repeat"]*sum(s["duration_ticks"] for s in self.sequence["segments"]) if self.sequence else 0

    def start(self, tick, private=None):
        if self.status == "active" and self.started_tick is None:
            self.started_tick = tick
            if private is not None:self.path_origin_m=private.get("motion_metrics",{}).get("path_length_m",0.0)

    def command(self, tick):
        """Authoritative body command source; no executable level callbacks."""
        if not self.sequence:return None
        elapsed=max(0,tick-self.started_tick) if self.started_tick is not None else 0
        cycle=sum(s["duration_ticks"] for s in self.sequence["segments"])
        if elapsed>=self.sequence_ticks:
            return {"linear":{"x":0.,"y":0.,"z":0.},"angular":{"x":0.,"y":0.,"z":0.}}
        offset=elapsed%cycle
        for segment in self.sequence["segments"]:
            if offset<segment["duration_ticks"]:return copy.deepcopy(segment["twist"])
            offset-=segment["duration_ticks"]

    def sequence_phase(self, tick):
        elapsed=max(0,tick-self.started_tick) if self.started_tick is not None else 0
        cycle=sum(s["duration_ticks"] for s in self.sequence["segments"])
        offset=elapsed%cycle
        for index,segment in enumerate(self.sequence["segments"]):
            if offset<segment["duration_ticks"]:
                return {"cycle_index":elapsed//cycle,"segment_index":index,"label":segment.get("label",str(index+1))}
            offset-=segment["duration_ticks"]

    def facts(self, private):
        return {"player_alive":private.get("player_alive",True),"objective_complete":False,"elapsed_ticks":self.elapsed_ticks,
                "moved":self.moved,"turned":self.turned,"hits":self.hits,"estimates":self.estimates,"target_alive":self.hp is None or self.hp>0,
                "sequence_complete":bool(self.sequence) and self.elapsed_ticks>=self.sequence_ticks,
                "controller_faulted":self.controller_faulted,
                "origin_distance_m":self.origin_distance_m,"path_length_m":self.path_length_m,
                **{key:value if value is not None else math.inf for key,value in self.diagnostics.report().items()}}

    def outcome(self, private, tick):
        if self.status != "active" or (self.started_tick is None and not (self.sequence and self.deployment_armed)):
            return None
        self.elapsed_ticks = tick-self.started_tick if self.started_tick is not None else 0
        completed = self.observe(private)
        self.player_hp = private.get("player_hp")
        from .level_rules import evaluate
        facts={**self.facts(private),"objective_complete":completed}
        parameters={**self.definition["rules"]["parameters"],"limit_ticks":self.limit_ticks}
        for outcome in self.definition["rules"]["outcomes"]:
            if evaluate(outcome["when"],facts,parameters):return outcome["reason"]
        return None

    def estimate(self, message, truth):
        if self.status != "active" or self.started_tick is None or message["simulation_tick"] <= self.last_estimate_tick:
            return
        source=self.definition["evaluation"].get("source","target_estimate")
        if (message.get("schema")=="pose2d@1")!=(source=="player_pose"):
            return
        if source=="player_pose" and (message.get("frame_id")!="map" or truth is None or message["simulation_tick"]<self.started_tick):
            return
        self.last_estimate_tick = message["simulation_tick"]
        self.estimates += 1
        self.diagnostics.observe(message["payload"],truth)
        self.error_count=self.diagnostics.counts.get("rmse_m",0)
        self.squared_error=self.diagnostics.squared.get("rmse_m",0.0)
        self.yaw_error_count=self.diagnostics.counts.get("yaw_rmse_rad",0)
        self.yaw_squared_error=self.diagnostics.squared.get("yaw_rmse_rad",0.0)

    def reference_estimate(self, message, truth):
        if (self.status!="active" or self.started_tick is None or truth is None or message["frame_id"]!="map"
                or message["simulation_tick"]<self.started_tick or message["simulation_tick"]<=self.reference_last_tick):
            return
        self.reference_last_tick=message["simulation_tick"]
        self.reference_diagnostics.observe(message["payload"],truth)

    def metric_report(self):
        result=self.diagnostics.report()
        if self.definition["evaluation"].get("reference_module_id"):
            result.update({"reference_"+key:value for key,value in self.reference_diagnostics.report().items()})
        return result

    def observe(self, private):
        if self.status != "active":
            return False
        p, origin = private["truth_pose"], self.config["scene"]["initial_pose"]
        from .level_rules import PROGRESS, evaluate
        parameters=self.definition["rules"]["parameters"]
        for key,spec in self.definition["rules"]["progress"].items():
            reached=PROGRESS[spec["type"]](p,origin)>=parameters[spec["parameter"]]
            setattr(self,key,(getattr(self,key) or reached) if spec["sticky"] else reached)
        target = next((item for item in private["targets"] if self.definition["target"] and item["target_id"] == self.definition["target"]["target_id"]),None)
        if target:
            self.hits = private["target_hits"].get(target["target_id"], 0)
            self.hp = target["hp"]
        if self.sequence:
            self.path_length_m=private["motion_metrics"]["path_length_m"]-self.path_origin_m
            self.origin_distance_m=math.hypot(p[0]-origin[0],p[1]-origin[1])
        facts=self.facts(private)
        if target:facts["target_alive"]=target["alive"]
        return evaluate(self.definition["rules"]["success"],facts,{**parameters,"limit_ticks":self.limit_ticks})

    def outcome_passed(self, reason):
        return next(o["result"]=="success" for o in self.definition["rules"]["outcomes"] if o["reason"]==reason)

    def finish(self, tick, *, passed=False, reason="aborted"):
        if self.status != "active":
            return self.public()
        self.status = "passed" if passed else "ended"
        if self.started_tick is not None:
            self.elapsed_ticks = tick-self.started_tick
        self.result = {"passed":passed,"reason":reason,"finished_tick":tick,"estimate_samples":self.estimates,
                       **self.metric_report(),"scored_samples":self.error_count,"hits":self.hits}
        if self.definition["evaluation"].get("reference_module_id"):
            self.result["reference_samples"]=self.reference_diagnostics.counts.get("rmse_m",0)
        if self.sequence:self.result.update(origin_distance_m=self.origin_distance_m,path_length_m=self.path_length_m)
        return self.public()

    def public(self):
        health_allowed = "view.enemy.health" in self.definition["capabilities"]
        state = {"level_id": self.level_id, "status": self.status, "enemy_hp": self.hp if health_allowed else None,
                "phase": "finished" if self.status != "active" else "preparing" if self.started_tick is None else "running",
                "timing": {"time_limit_s": self.definition["time_limit_s"], "start_on": self.definition["timer_start"],
                           "started_tick": self.started_tick, "elapsed_ticks": self.elapsed_ticks,
                           "remaining_s": max(0, self.limit_ticks-self.elapsed_ticks)/self.config["clock"]["physics_hz"]},
                "player_hp": self.player_hp if "view.player.health" in self.definition["capabilities"] else None,
                "player_max_hp": self.player_max_hp if "view.player.health" in self.definition["capabilities"] else None,
                "enemy_max_hp": (self.definition["target"] or {}).get("health", {}).get("max_hp") if health_allowed else None,
                "progress": {"moved": self.moved, "turned": self.turned,
                             "has_estimate": self.estimates > 0, "hit": self.hits > 0},
                "result": copy.deepcopy(self.result)}
        if state["result"]:
            allowed=self.definition["permissions"]["visualization"].get("allowed_metrics",[])
            for metric in ("reference_rmse_m","reference_yaw_rmse_rad"):
                if metric not in allowed:state["result"].pop(metric,None)
            if not set(allowed)&{"reference_rmse_m","reference_yaw_rmse_rad"}:
                state["result"].pop("reference_samples",None)
        if self.sequence:
            allowed=self.definition["permissions"]["visualization"].get("allowed_metrics",[])
            state["motion"]={key:getattr(self,key) for key in ("origin_distance_m","path_length_m") if key in allowed}
            state["motion"]["sequence_ticks"]=self.sequence_ticks
            command=self.command((self.started_tick or 0)+self.elapsed_ticks)
            state["motion"].update(command_vx_mps=command["linear"]["x"],command_wz_radps=command["angular"]["z"])
        feedback=self.definition["evaluation"].get("live_feedback")
        entries=feedback if isinstance(feedback,list) else [feedback] if feedback else []
        for entry in entries:
            metric=entry["metric"]
            if metric in self.definition["permissions"]["visualization"].get("allowed_metrics",[]):
                state.setdefault("live_metrics",{})[metric]=self.diagnostics.report()[metric]
                state["live_metrics"]["scored_samples"]=self.diagnostics.counts[metric]
                reference=entry.get("reference_metric")
                if reference and reference in self.definition["permissions"]["visualization"].get("allowed_metrics",[]):
                    state["live_metrics"][reference]=self.metric_report()[reference]
                    state["live_metrics"]["reference_samples"]=self.reference_diagnostics.counts[metric]
        return state
