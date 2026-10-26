"""Authority-only intercepted GPS. Independent RNG never changes the existing Radar stream."""
import math
import random


class GpsInterceptSimulator:
    def __init__(self, config):
        self.config = config
        definition = config.get("campaign", {}).get("levels", {}).get(config.get("campaign", {}).get("active_level"))
        self.sensor = next((s for s in definition["sensors"] if s["type"] == "intercepted_gps"), None) if definition else None
        self.last_tick = None
        if self.sensor:
            self.random = random.Random(f"{config['runtime']['seed']}:{self.sensor['parameters']['random_stream']}")

    def sample(self, private, tick):
        if not self.sensor or self.last_tick == tick or tick % (self.config["clock"]["physics_hz"] // self.sensor["update_hz"]):
            return None
        self.last_tick = tick
        params = self.sensor["parameters"]
        points = []
        own_x, own_y, _ = private["truth_pose"]
        for target in private["targets"]:
            if target["target_id"] != params["target_robot"] or not target["alive"]:
                continue
            x, y, yaw = target["pose"]
            from .chassis_profiles import target_geometry
            definition=next(t for t in self.config["weapons"]["targets"] if t["target_id"]==target["target_id"])
            dx,dy=target_geometry(self.config,definition)["gps_mount_m"]
            x, y = x + dx*math.cos(yaw)-dy*math.sin(yaw), y + dx*math.sin(yaw)+dy*math.cos(yaw)
            if math.hypot(x-own_x, y-own_y) > params["range_m"]:
                continue
            noise = params["noise"]
            if self.random.random() < noise["drop_probability"]:
                continue
            points.append([x+self.random.gauss(0,noise["position_stddev_m"]),y+self.random.gauss(0,noise["position_stddev_m"])])
        return {"positions_m": points}
