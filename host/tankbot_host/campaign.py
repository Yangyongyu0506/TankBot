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
    if [lid for chapter in chapters for lid in chapter["levels"]]!=list(c["levels"]):
        raise ValueError("Chapters must contain every level once in progression order")
    for lid,level in c["levels"].items():
        if type(level["time_limit_s"]) is not int or level["time_limit_s"]<=0:
            raise ValueError("Each level requires a positive time_limit_s")
        if level["armor_mode"]!=bool(level["target"].get("armor")):
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
    c["weapons"]["enabled"]=True
    c["weapons"]["targets"]=[copy.deepcopy(level["target"])]
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
    apply_profiles(c)
    validate_profile(c)
    return c


def catalog(config):
    result = []
    for key, value in config.get("campaign", {}).get("levels", {}).items():
        item = {"level_id": key, **{name: copy.deepcopy(value[name]) for name in ("title", "problem", "hints", "capabilities", "objective", "time_limit_s", "timer_start")},
                "chapter_id":value.get("chapter_id"),"control_sources":copy.deepcopy(value.get("control_sources")),"armor_mode":value.get("armor_mode",False),"ui":copy.deepcopy(value["tutorial"]["lesson"]["ui"]),"visualization":copy.deepcopy(value["visualization"]),"allowed_layers":copy.deepcopy(value["permissions"]["visualization"]["allowed_layers"])}
        item["problem"] = item["problem"].format(time_limit_s=value["time_limit_s"], max_hp=value["target"].get("health", {}).get("max_hp"))
        feedback=value["evaluation"].get("live_feedback")
        if feedback and feedback["metric"] in value["permissions"]["visualization"].get("allowed_metrics",[]):
            item["live_feedback"]=copy.deepcopy(feedback)
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
        self.hp = self.definition["target"].get("health", {}).get("max_hp")
        self.estimates = 0
        self.last_estimate_tick = -1
        self.squared_error = 0.0
        self.error_count = 0
        self.yaw_squared_error = 0.0
        self.yaw_error_count = 0
        from .level_rules import Diagnostics
        self.diagnostics = Diagnostics(self.definition["evaluation"])
        self.started_tick = None
        self.elapsed_ticks = 0
        self.limit_ticks = self.definition["time_limit_s"] * config["clock"]["physics_hz"]
        self.player_max_hp = config["scene"].get("player_health", {}).get("max_hp") if config["scene"].get("player_health") else None
        self.player_hp = self.player_max_hp

    def start(self, tick):
        if self.status == "active" and self.started_tick is None:
            self.started_tick = tick

    def outcome(self, private, tick):
        if self.status != "active" or self.started_tick is None:
            return None
        self.elapsed_ticks = tick-self.started_tick
        completed = self.observe(private)
        self.player_hp = private.get("player_hp")
        from .level_rules import evaluate
        facts={"player_alive":private.get("player_alive",True),"objective_complete":completed,"elapsed_ticks":self.elapsed_ticks,
               "moved":self.moved,"turned":self.turned,"hits":self.hits,"estimates":self.estimates,"target_alive":self.hp is None or self.hp>0}
        parameters={**self.definition["rules"]["parameters"],"limit_ticks":self.limit_ticks}
        for outcome in self.definition["rules"]["outcomes"]:
            if evaluate(outcome["when"],facts,parameters):return outcome["reason"]
        return None

    def estimate(self, message, truth):
        if self.status != "active" or self.started_tick is None or message["simulation_tick"] <= self.last_estimate_tick:
            return
        self.last_estimate_tick = message["simulation_tick"]
        self.estimates += 1
        self.diagnostics.observe(message["payload"],truth)
        self.error_count=self.diagnostics.counts.get("rmse_m",0)
        self.squared_error=self.diagnostics.squared.get("rmse_m",0.0)
        self.yaw_error_count=self.diagnostics.counts.get("yaw_rmse_rad",0)
        self.yaw_squared_error=self.diagnostics.squared.get("yaw_rmse_rad",0.0)

    def observe(self, private):
        if self.status != "active":
            return False
        p, origin = private["truth_pose"], self.config["scene"]["initial_pose"]
        from .level_rules import PROGRESS, evaluate
        parameters=self.definition["rules"]["parameters"]
        for key,spec in self.definition["rules"]["progress"].items():
            reached=PROGRESS[spec["type"]](p,origin)>=parameters[spec["parameter"]]
            setattr(self,key,(getattr(self,key) or reached) if spec["sticky"] else reached)
        target = next(item for item in private["targets"] if item["target_id"] == self.definition["target"]["target_id"])
        self.hits = private["target_hits"].get(target["target_id"], 0)
        self.hp = target["hp"]
        facts={"moved":self.moved,"turned":self.turned,"hits":self.hits,"estimates":self.estimates,
               "target_alive":target["alive"],"player_alive":private.get("player_alive",True),"objective_complete":False,"elapsed_ticks":self.elapsed_ticks}
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
                       **self.diagnostics.report(),"scored_samples":self.error_count,"hits":self.hits}
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
                "enemy_max_hp": self.definition["target"].get("health", {}).get("max_hp") if health_allowed else None,
                "progress": {"moved": self.moved, "turned": self.turned,
                             "has_estimate": self.estimates > 0, "hit": self.hits > 0},
                "result": copy.deepcopy(self.result)}
        feedback=self.definition["evaluation"].get("live_feedback")
        if feedback and feedback["metric"] in self.definition["permissions"]["visualization"].get("allowed_metrics",[]):
            metric=feedback["metric"]
            state["live_metrics"]={metric:self.diagnostics.report()[metric],"scored_samples":self.diagnostics.counts[metric]}
        return state
