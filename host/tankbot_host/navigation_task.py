"""Authority-owned ordered waypoint evaluation. Only public goals leave this module."""
import copy
import math


class WaypointRoute:
    def __init__(self, specification):
        self.spec = copy.deepcopy(specification)
        self.goal_index = 0
        self.reached_count = 0
        self.settled_ticks = 0
        self.stable_since = None
        self.last_tick = None
        self.complete = False

    def goal(self):
        return {"goal_index": self.goal_index, "position_m": list(self.spec["points_m"][self.goal_index])}

    def observe(self, pose, velocity, tick):
        if self.complete or (self.last_tick is not None and tick <= self.last_tick):
            return
        if self.last_tick is not None and tick != self.last_tick + 1:
            self.stable_since = None
        self.last_tick = tick
        target = self.spec["points_m"][self.goal_index]
        within = math.hypot(pose[0]-target[0], pose[1]-target[1]) <= self.spec["position_tolerance_m"]
        if within:
            self.reached_count = max(self.reached_count, self.goal_index+1)
            if self.goal_index < len(self.spec["points_m"])-1:
                self.goal_index += 1
                self.stable_since = None
                self.settled_ticks = 0
                return  # At most one checkpoint per physical tick.
        stopped = (within and math.hypot(velocity[0], velocity[1]) <= self.spec["stop_linear_speed_mps"]
                   and abs(velocity[2]) <= self.spec["stop_yaw_rate_radps"])
        if not stopped:
            self.stable_since = None
            self.settled_ticks = 0
            return
        if self.stable_since is None:
            self.stable_since = tick
        self.settled_ticks = tick-self.stable_since
        self.complete = self.settled_ticks >= self.spec["stop_duration_ticks"]

    def phase(self):
        return {"cycle_index": 0, "segment_index": self.goal_index,
                "label": f"航点 {self.goal_index+1}"}

    def public(self):
        return {"goal_index": self.goal_index, "reached_count": self.reached_count,
                "total": len(self.spec["points_m"]), "settled_ticks": self.settled_ticks,
                "required_settle_ticks": self.spec["stop_duration_ticks"], "complete": self.complete}
