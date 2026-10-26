"""Authority-only intercepted GPS. Independent RNG never changes the existing Radar stream."""
import math
import random


class ArmorDetectionSimulator:
    """Anonymous nearest visible armor centers; no IDs, center fix or true heading."""
    def __init__(self,config):
        self.config=config
        definition=config.get("campaign",{}).get("levels",{}).get(config.get("campaign",{}).get("active_level"))
        self.sensor=next((s for s in definition["sensors"] if s["type"]=="armor_detector"),None) if definition else None
        self.last_tick=None
        if self.sensor:
            self.random=random.Random(f"{config['runtime']['seed']}:{self.sensor['parameters']['random_stream']}")

    def sample(self,private,tick):
        if not self.sensor or self.last_tick==tick or tick%(self.config["clock"]["physics_hz"]//self.sensor["update_hz"]):
            return None
        self.last_tick=tick
        from .campaign import blocked
        from .chassis_profiles import target_geometry
        params=self.sensor["parameters"]
        own_x,own_y,own_yaw=private["truth_pose"]
        candidates=[]
        for target in private["targets"]:
            if target["target_id"]!=params["target_robot"] or not target["alive"]:
                continue
            definition=next(t for t in self.config["weapons"]["targets"] if t["target_id"]==target["target_id"])
            x,y,yaw=target["pose"];c,s=math.cos(yaw),math.sin(yaw)
            for mx,my,normal_yaw in target_geometry(self.config,definition)["armor_mounts"]:
                px,py=x+c*mx-s*my,y+s*mx+c*my
                dx,dy=px-own_x,py-own_y
                if math.cos(yaw+normal_yaw)*(-dx)+math.sin(yaw+normal_yaw)*(-dy)<=0:
                    continue
                distance=math.hypot(dx,dy)
                if distance>params["range_m"] or blocked((own_x,own_y),(px,py),self.config["scene"]["walls"]):
                    continue
                bearing=(math.atan2(dy,dx)-own_yaw+math.pi)%math.tau-math.pi
                if abs(bearing)>params["field_of_view_rad"]/2:
                    continue
                candidates.append((distance,bearing))
        noise=params["noise"];points=[]
        # Equal ranges use bearing, never the physical plate index, as a tie-break.
        tolerance=self.config["validation"]["numeric_tolerance"]
        for distance,bearing in sorted(candidates,key=lambda item:(round(item[0]/tolerance),item[1]))[:params["max_detections"]]:
            if self.random.random()<noise["drop_probability"]:
                continue
            distance=max(0.,distance+self.random.gauss(0.,noise["range_stddev_m"]))
            bearing=(bearing+self.random.gauss(0.,noise["bearing_stddev_rad"])+math.pi)%math.tau-math.pi
            points.append([distance,bearing])
        return {"measurements_rt":points}


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
