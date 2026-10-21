"""Estimated-only selector and view projection. Neither class accepts a World/truth object."""
import copy


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
        if policy["system_pose_allowed"]:
            raise ValueError("System Pose Provider is not implemented in M1")
        self.policy = copy.deepcopy(policy)

    def build(self, tick, revision, selector, sensors):
        policy = self.policy
        selected = None
        candidate = selector.canonical
        if policy["player_pose_allowed"] and candidate:
            age = tick-candidate["simulation_tick"]
            if candidate["frame_id"] in policy["allowed_pose_frames"] and 0 <= age <= policy["pose_hide_after_ticks"]:
                selected = {"source_id": selector.source_id, "frame_id": candidate["frame_id"],
                            "simulation_tick": candidate["simulation_tick"], "freshness": "fresh" if age <= policy["pose_fresh_ticks"] else "stale",
                            "pose": copy.deepcopy(candidate["payload"])}
        observations = [copy.deepcopy(sensors[c]) for c in policy["local_observation_channels"] if c in sensors]
        return {"view_revision": revision, "policy_id": policy["policy_id"], "selected_pose": selected,
                "local_observations": observations, "objects": [], "effects": []}
