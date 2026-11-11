"""Verification-only A*: heuristic frontier, g-score relaxation and parent tree."""
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
        cost, parent, closed = {start:0.}, {}, set()
        frontier = [(math.dist(start,goal)*geo.data.resolution_m,0.,start)]
        while frontier:
            _, distance, node = heapq.heappop(frontier)
            if node in closed or distance != cost[node]:
                continue
            if node == goal:
                return geo.finish(parent,start,goal,start_xy,goal_xy)
            closed.add(node)
            for neighbour, step in geo.neighbours(node):
                candidate = distance+step
                if neighbour not in closed and candidate < cost.get(neighbour,math.inf):
                    cost[neighbour], parent[neighbour] = candidate, node
                    heuristic = math.dist(neighbour,goal)*geo.data.resolution_m
                    heapq.heappush(frontier,(candidate+heuristic,candidate,neighbour))
        return None
