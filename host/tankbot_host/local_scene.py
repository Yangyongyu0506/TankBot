"""Bounded trusted obstacle preparation. Public prior geometry is never overwritten."""
import hashlib
import heapq
import math
import random
import numpy as np
from .global_planning import PlanningError, map_grid, SafeGrid, safe_task, reference_distances
from .path_generation import canonical


def reference_route(safe, start, goal, max_nodes):
    """Private eight-neighbour A*, independent of any player implementation."""
    origin, target = safe.map.world_to_grid(start), safe.map.world_to_grid(goal)
    distances, parents = {origin: 0.}, {}
    queue = [(math.dist(origin, target), 0., origin)]
    visited = 0
    h, w = safe.blocked.shape
    while queue:
        _, cost, cell = heapq.heappop(queue)
        if cost != distances[cell]:
            continue
        visited += 1
        if visited > max_nodes:
            raise PlanningError('LOCAL_SCENE_NODE_LIMIT: 私有参考搜索超过节点上限')
        if cell == target:
            result = [goal]
            while cell != origin:
                result.append(safe.map.grid_to_world(*cell).tolist())
                cell = parents[cell]
            result.append(start)
            return np.asarray(result[::-1])
        row, col = cell
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            nr, nc = row+dy, col+dx
            if not (0 <= nr < h and 0 <= nc < w) or safe.blocked[nr, nc]:
                continue
            if dy and dx and (safe.blocked[row,nc] or safe.blocked[nr,col]):
                continue
            value = cost+math.hypot(dy,dx)
            if value < distances.get((nr,nc), math.inf):
                distances[nr,nc], parents[nr,nc] = value, cell
                heapq.heappush(queue,(value+math.dist((nr,nc),target),value,(nr,nc)))
    raise PlanningError('LOCAL_SCENE_NO_ROUTE: 先验任务不可达')


def rectangle_distance(point, center, size):
    return float(np.linalg.norm(np.maximum(np.abs(np.asarray(point)-center)-size/2, 0)))


def physical_walls(config):
    return [*config['scene']['walls'], *config.get('private_obstacles', {}).get('walls', [])]


def prepare_local_scene(config):
    level = config.get('campaign', {}).get('levels', {}).get(config.get('campaign', {}).get('active_level'))
    spec = level['rules'].get('local_navigation') if level else None
    if not spec:
        return
    task = config['navigation_planning']
    safe = safe_task(task)
    p = spec['obstacle']
    route = reference_route(safe, task['start_xy'], task['goal_xy'], p['max_search_nodes'])
    # Remove staircase artefacts by private line-of-sight shortcuts, so obstacle
    # placement covers a common safe route without consulting the player's path.
    simple, index = [route[0]], 0
    while index < len(route)-1:
        end = len(route)-1
        while end > index+1 and not safe.segment_safe(route[index],route[end]):
            end -= 1
        simple.append(route[end]); index = end
    samples = []
    for a,b in zip(simple,simple[1:]):
        count = max(1, math.ceil(math.dist(a,b)/task['map']['resolution_m']))
        samples.extend(a+(b-a)*(i/count) for i in range(count))
    random.Random(f"{config['runtime']['seed']}:{p['random_stream']}:{p['generation_version']}").shuffle(samples)
    walls = config['scene']['walls']
    bounds = task['map']['field_bounds_m']
    side = p['size_m']
    for center in samples[:p['max_attempts']]:
        if (np.any(center-side/2 < bounds[:2]) or np.any(center+side/2 > bounds[2:])
                or any(rectangle_distance(xy,center,side) < p['min_endpoint_clearance_m'] for xy in (task['start_xy'],task['goal_xy']))):
            continue
        if any(np.all(np.abs(center-np.asarray(w['center'])) <= (side+np.asarray(w['size']))/2) for w in walls):
            continue
        obstacle = {'center':center.tolist(), 'size':[side,side]}
        data,_ = map_grid([*walls,obstacle], task['map']['resolution_m'], level['rules']['global_planning']['max_grid_cells'])
        full = SafeGrid(data, task['robot_radius_m'], task['safety_margin_m'])
        try:
            distances = reference_distances(full,task['start_xy'],p['max_search_nodes'])
        except PlanningError:
            continue
        if data.world_to_grid(task['goal_xy']) not in distances:
            continue
        value = {'walls':[obstacle], 'generation_version':p['generation_version'],
                 'identity':hashlib.sha256(canonical({'task':task['task_id'],'parameters':p,'walls':[obstacle]}).encode()).hexdigest()}
        if config.get('private_obstacles') not in (None,value):
            raise PlanningError('LOCAL_SCENE_IDENTITY_MISMATCH')
        config['private_obstacles'] = value
        return
    raise PlanningError('LOCAL_SCENE_GENERATION_FAILED: 在配置上限内无法放置安全可绕行的静态障碍')
