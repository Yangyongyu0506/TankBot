"""Verification-only Dijkstra: settle vertices by distance, without a heuristic."""
import heapq
import math
from navigation.planning_geometry import PlanningGeometry


class GlobalPlanner:
    def __init__(self, map_data, robot_radius_m, safety_margin_m):
        self.geometry = PlanningGeometry(map_data,robot_radius_m,safety_margin_m)

    def plan(self, start_xy, goal_xy):
        geo = self.geometry
        start, goal = geo.data.world_to_grid(start_xy), geo.data.world_to_grid(goal_xy)
        if geo.blocked[start] or geo.blocked[goal]:
            return None
        distances, parent = {start:0.}, {}
        queue = [(0.,start)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            if node == goal:
                return geo.finish(parent,start,goal,start_xy,goal_xy)
            for neighbour, step in geo.neighbours(node):
                candidate = distance+step
                if candidate < distances.get(neighbour,math.inf):
                    distances[neighbour], parent[neighbour] = candidate, node
                    heapq.heappush(queue,(candidate,neighbour))
        return None
