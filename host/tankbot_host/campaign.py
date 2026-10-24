"""Trusted lesson configuration, sensor simulation and end-of-attempt evaluation."""
import copy
import math
import random
import importlib.util


def active(config):
    return config.get("campaign", {}).get("active_level")


def ensure_native_numpy() -> None:
    if importlib.util.find_spec("numpy") is None:
        raise ValueError("教学关卡需要 NumPy。请在运行游戏的 Python 虚拟环境执行：python -m pip install -r requirements.txt")


def validate_profile(config):
    if "campaign" not in config:
        return
    c = config["campaign"]
    from .learning import LESSONS
    if set(c["levels"]) - LESSONS.keys():
        raise ValueError("Every level requires a complete learning guide")
    r = c["radar"]
    if config["clock"]["physics_hz"] % r["update_hz"] or config["clock"]["sensor_hz"] % r["update_hz"]:
        raise ValueError("Radar rate must divide physics and sensor rates")
    if r["mount_m"] != [0, 0] or r["yaw_rad"] != 0:
        raise ValueError("M4 supports only the confirmed center-aligned Radar")
    if any(r["profiles"]["ideal"].values()):
        raise ValueError("C1 requires an ideal Radar")
    if config["view_mode"] == "campaign" and not active(config):
        raise ValueError("Campaign mode requires an active level")
    required = {"system.pose.read", "estimate.target.publish", "control.manual.drive", "control.manual.turret", "control.manual.fire"}
    for level_id, level in c["levels"].items():
        caps = set(level["capabilities"])
        if not required <= caps:
            raise ValueError("M4 requires self-pose, target publication and manual controls")
        if (level["radar_profile"] is not None) != ("sensor.radar.read" in caps):
            raise ValueError("Radar profile and capability disagree")
        if level_id != "c0" and caps & {"view.enemy.truth", "view.projectiles.truth"}:
            raise ValueError("C1/C2 cannot grant enemy or projectile truth")


def configure(config, level_id):
    """Resolve trusted lesson data. Never accept a player-supplied policy or model."""
    if level_id not in config.get("campaign", {}).get("levels", {}):
        raise ValueError("UNKNOWN_LEVEL")
    c = copy.deepcopy(config)
    campaign = c["campaign"]
    campaign["active_level"] = level_id
    level = campaign["levels"][level_id]
    c["view_mode"] = "campaign"
    c["module"].update(module_id=campaign["module_id"], entry_point=campaign["entry_point"], fault="none")
    c["module"]["weapon_demo"]["enabled"] = False
    c["control_sources"] = {"chassis": "keyboard", "turret": "keyboard", "weapon": "keyboard"}
    c["scene"].update(initial_pose=campaign["initial_pose"], initial_velocity=campaign["initial_velocity"],
                       public_initial_pose=True, public_map=True)
    c["weapons"]["enabled"] = True
    c["weapons"]["targets"] = [copy.deepcopy(level["target"])]
    c["view"]["pose_source_id"] = "system"
    caps = set(level["capabilities"])
    c["view_policy"].update(policy_id="campaign-" + level_id, system_pose_allowed=True, player_pose_allowed=False,
        target_estimates_allowed=True, true_enemy_objects="view.enemy.truth" in caps,
        world_effects="view.projectiles.truth" in caps,
        local_observation_channels=["/robot/sensors/joint_states", "/robot/sensors/imu",
                                    "/robot/turret/joint_states", "/robot/weapons/cannon/state"] +
                                   (["/robot/sensors/radar"] if "sensor.radar.read" in caps else []))
    validate_profile(c)
    return c


def catalog(config):
    return [{"level_id": key, **{name: copy.deepcopy(value[name]) for name in ("title", "problem", "hints", "capabilities", "objective")}}
            for key, value in config.get("campaign", {}).get("levels", {}).items()]


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
        self.noise = self.settings["profiles"][profile] if profile else None
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

    def estimate(self, message, truth):
        if self.status != "active" or message["simulation_tick"] <= self.last_estimate_tick:
            return
        self.last_estimate_tick = message["simulation_tick"]
        self.estimates += 1
        if truth is not None:
            point = message["payload"]
            error = math.hypot(point["x_m"]-truth[0], point["y_m"]-truth[1])
            self.squared_error += error*error
            self.error_count += 1

    def observe(self, private):
        if self.status != "active":
            return False
        p, origin = private["truth_pose"], self.config["scene"]["initial_pose"]
        objective = self.definition["objective"]
        self.moved |= math.hypot(p[0]-origin[0], p[1]-origin[1]) >= objective["movement_m"]
        self.turned |= abs((p[2]-origin[2]+math.pi) % math.tau-math.pi) >= objective["turn_rad"]
        target = next(item for item in private["targets"] if item["target_id"] == self.definition["target"]["target_id"])
        self.hits = private["target_hits"].get(target["target_id"], 0)
        self.hp = target["hp"]
        if self.level_id == "c2":
            return not target["alive"]
        return self.moved and self.turned and self.hits >= objective["required_hits"] and self.estimates >= objective["required_estimates"]

    def finish(self, tick, *, passed=False):
        if self.status != "active":
            return self.public()
        self.status = "passed" if passed else "ended"
        rmse = math.sqrt(self.squared_error/self.error_count) if self.error_count else None
        self.result = {"passed": passed, "finished_tick": tick, "estimate_samples": self.estimates,
                       "rmse_m": rmse if rmse is None or math.isfinite(rmse) else None,
                       "scored_samples": self.error_count, "hits": self.hits}
        return self.public()

    def public(self):
        health_allowed = "view.enemy.health" in self.definition["capabilities"]
        return {"level_id": self.level_id, "status": self.status, "enemy_hp": self.hp if health_allowed else None,
                "enemy_max_hp": self.definition["target"].get("health", {}).get("max_hp") if health_allowed else None,
                "progress": {"moved": self.moved, "turned": self.turned,
                             "has_estimate": self.estimates > 0, "hit": self.hits > 0},
                "result": copy.deepcopy(self.result)}
