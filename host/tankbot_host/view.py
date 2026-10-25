"""Estimated-only selector and view projection. Neither class accepts a World/truth object."""
import copy
import math
import json


class PoseSelector:
    def __init__(self, source_id):
        self.source_id = source_id
        self.canonical = None

    def accept(self, source_id, candidate, message_factory):
        if source_id != self.source_id:
            return
        self.canonical = message_factory("pose2d@1", "/robot/localization/pose", copy.deepcopy(candidate["payload"]),
                                         frame=candidate["frame_id"], publisher="pose_selector", tick=candidate["simulation_tick"])


class ViewGateway:
    def __init__(self, policy):
        self.policy = copy.deepcopy(policy)

    def robot_topics(self, cache, max_bytes):
        if not self.policy.get("robot_topics_allowed",False):
            return []
        result, size = [],0
        for message in sorted(cache.values(),key=lambda m:(-m["simulation_tick"],m["channel"])):
            length = len(json.dumps(message,ensure_ascii=False).encode())
            if size+length <= max_bytes:
                result.append(copy.deepcopy(message))
                size += length
        return result

    def build(self, tick, revision, selector, sensors, *, practice=None, target_estimate=None, campaign=False):
        policy = self.policy
        selected = None
        candidate = selector.canonical
        if candidate and ((selector.source_id == "system" and policy["system_pose_allowed"]) or (selector.source_id != "system" and policy["player_pose_allowed"])):
            age = tick-candidate["simulation_tick"]
            if candidate["frame_id"] in policy["allowed_pose_frames"] and 0 <= age <= policy["pose_hide_after_ticks"]:
                selected = {"source_id": selector.source_id, "frame_id": candidate["frame_id"],
                            "simulation_tick": candidate["simulation_tick"], "freshness": "fresh" if age <= policy["pose_fresh_ticks"] else "stale",
                            "pose": copy.deepcopy(candidate["payload"])}
        objects=[copy.deepcopy(obj) for obj in practice["objects"] if (obj["kind"]=="projectile" and policy["world_effects"]) or (obj["kind"]=="target" and policy["true_enemy_objects"])] if practice is not None else []
        observations = [copy.deepcopy(sensors[c]) for c in policy["local_observation_channels"] if c in sensors]
        payload = {"view_revision": revision, "policy_id": policy["policy_id"], "selected_pose": selected,
                   "local_observations": observations, "objects": objects, "effects": []}
        if campaign:
            payload["target_estimates"] = []
            if (policy.get("target_estimates_allowed", False) and target_estimate is not None
                    and target_estimate["frame_id"] == "map"
                    and 0 <= tick-target_estimate["simulation_tick"] <= policy["pose_hide_after_ticks"]):
                payload["target_estimates"].append(copy.deepcopy(target_estimate))
        return payload


class SystemPoseProvider:
    """Authority-only projection; the private DTO never goes directly to ViewGateway."""
    @staticmethod
    def pose(private, config, *, runtime_authorized=False):
        if not runtime_authorized and (not config["view_policy"]["system_pose_allowed"] or "map" not in config["view_policy"]["allowed_pose_frames"]):
            raise ValueError("System self-pose denied")
        x, y, yaw = private["truth_pose"]
        return {"x_m": x, "y_m": y, "yaw_rad": yaw, "covariance": None, "child_frame_id": "base_link"}

    @staticmethod
    def project(private,config,tick):
        policy=config["view_policy"]
        if config["view_mode"] not in ("weapons-practice", "campaign") or not (policy["world_effects"] or policy["true_enemy_objects"]):
            raise ValueError("Truth projection denied")
        def pose(value):
            return {"x_m":value[0],"y_m":value[1],"yaw_rad":value[2],"covariance":None,"child_frame_id":"base_link"}
        objects=[{"kind":"projectile","projectile_id":p["projectile_id"],"x_m":p["position"][0],"y_m":p["position"][1],
                  "radius_m":config["weapons"]["projectile"]["radius_m"]} for p in private["projectiles"]]
        if config["weapons"]["enabled"]:
            objects += [{"kind":"target","target_id":t["target_id"],"pose":{"x_m":t["pose"][0],"y_m":t["pose"][1],"yaw_rad":(t["pose"][2]+math.pi)%math.tau-math.pi},"hits":private["target_hits"][t["target_id"]]}
                        for t in private["targets"] if t["alive"]]
        return {"pose":pose(private["truth_pose"]),"objects":objects}
