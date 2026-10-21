"""Estimated-only selector and view projection. Neither class accepts a World/truth object."""
import copy
import math


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

    def build(self, tick, revision, selector, sensors, *, practice=None):
        policy = self.policy
        selected = None
        candidate = selector.canonical
        if candidate and ((selector.source_id == "system" and policy["system_pose_allowed"]) or (selector.source_id != "system" and policy["player_pose_allowed"])):
            age = tick-candidate["simulation_tick"]
            if candidate["frame_id"] in policy["allowed_pose_frames"] and 0 <= age <= policy["pose_hide_after_ticks"]:
                selected = {"source_id": selector.source_id, "frame_id": candidate["frame_id"],
                            "simulation_tick": candidate["simulation_tick"], "freshness": "fresh" if age <= policy["pose_fresh_ticks"] else "stale",
                            "pose": copy.deepcopy(candidate["payload"])}
        objects=copy.deepcopy(practice["objects"]) if practice is not None and policy["world_effects"] else []
        observations = [copy.deepcopy(sensors[c]) for c in policy["local_observation_channels"] if c in sensors]
        return {"view_revision": revision, "policy_id": policy["policy_id"], "selected_pose": selected,
                "local_observations": observations, "objects": objects, "effects": []}


class SystemPoseProvider:
    """Authority-only projection; the private DTO never goes directly to ViewGateway."""
    @staticmethod
    def project(private,config,tick):
        policy=config["view_policy"]
        if config["view_mode"]!="weapons-practice" or not policy["system_pose_allowed"] or not policy["world_effects"] or "map" not in policy["allowed_pose_frames"]:
            raise ValueError("Truth projection denied")
        def pose(value):
            return {"x_m":value[0],"y_m":value[1],"yaw_rad":value[2],"covariance":None,"child_frame_id":"base_link"}
        objects=[{"kind":"projectile","projectile_id":p["projectile_id"],"x_m":p["position"][0],"y_m":p["position"][1],
                  "radius_m":config["weapons"]["projectile"]["radius_m"]} for p in private["projectiles"]]
        if config["weapons"]["enabled"]:
            objects += [{"kind":"target","target_id":t["target_id"],"pose":{"x_m":t["pose"][0],"y_m":t["pose"][1],"yaw_rad":(t["pose"][2]+math.pi)%math.tau-math.pi},"hits":private["target_hits"][t["target_id"]]}
                        for t in config["weapons"]["targets"]]
        return {"pose":pose(private["truth_pose"]),"objects":objects}
