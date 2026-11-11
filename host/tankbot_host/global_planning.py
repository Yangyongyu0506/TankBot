"""Trusted known-map task preparation and independent path validation; never a player helper."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import hashlib
import heapq
import json
import math
import random
import numpy as np
from tankbot.maps import OccupancyGrid
from .path_generation import canonical, segment_box_intersection


class PlanningError(ValueError):
    pass


def map_grid(walls, resolution_m, max_cells):
    """One source of field bounds, coverage and rasterisation for judge, SDK and UI."""
    if not walls:
        raise PlanningError("PLANNING_MAP_BOUNDS: 地图必须包含可解析的有限边界")
    boxes = np.array([[w['center'][0]-w['size'][0]/2, w['center'][1]-w['size'][1]/2,
                       w['center'][0]+w['size'][0]/2, w['center'][1]+w['size'][1]/2] for w in walls])
    bounds = np.concatenate((boxes[:, :2].min(axis=0), boxes[:, 2:].max(axis=0)))
    origin = bounds[:2]
    dimensions = [int(((Decimal(str(float(bounds[i+2])))-Decimal(str(float(bounds[i])))) /
                       Decimal(str(resolution_m))).to_integral_value(rounding=ROUND_CEILING)) for i in range(2)]
    width, height = dimensions
    if width*height > max_cells or min(width, height) < 1:
        raise PlanningError("PLANNING_GRID_LIMIT: 网格覆盖超过配置容量")
    raw = np.zeros((height, width), dtype=np.bool_)
    # Closed cell rectangles: touching either a wall or the outside is occupied.
    x = origin[0]+np.arange(width)*resolution_m
    y = origin[1]+np.arange(height)*resolution_m
    for left, bottom, right, top in boxes:
        columns = (x <= np.nextafter(right, math.inf)) & (x+resolution_m >= np.nextafter(left, -math.inf))
        rows = (y <= np.nextafter(top, math.inf)) & (y+resolution_m >= np.nextafter(bottom, -math.inf))
        raw[np.ix_(rows, columns)] = True
    raw[:, x+resolution_m > np.nextafter(bounds[2], math.inf)] = True
    raw[y+resolution_m > np.nextafter(bounds[3], math.inf), :] = True
    return OccupancyGrid(raw, origin, resolution_m), bounds.tolist()


def inflate_grid(raw, cells):
    """Normative square dilation, with outside padded as occupied."""
    padded = np.pad(raw, cells, constant_values=True)
    result = np.zeros(raw.shape, dtype=np.bool_)
    h, w = raw.shape
    for row in range(2*cells+1):
        for col in range(2*cells+1):
            result |= padded[row:row+h, col:col+w]
    return result


class SafeGrid:
    def __init__(self, data, radius, margin):
        self.map = data
        self.cells = math.ceil((radius+margin)/data.resolution_m)
        self.blocked = inflate_grid(data.grid, self.cells)

    def segment_safe(self, a, b):
        data, resolution = self.map, self.map.resolution_m
        try:
            data.world_to_grid(a); data.world_to_grid(b)
        except (IndexError, ValueError):
            return False
        # Include neighbouring cells before closed slab tests, so exact grid
        # lines/corners cannot be accepted by a floor convention or tolerance.
        low = np.floor((np.minimum(a, b)-data.origin_xy)/resolution).astype(int)-1
        high = np.floor((np.maximum(a, b)-data.origin_xy)/resolution).astype(int)+1
        for row in range(max(0, low[1]), min(data.grid.shape[0]-1, high[1])+1):
            for col in range(max(0, low[0]), min(data.grid.shape[1]-1, high[0])+1):
                if not self.blocked[row, col]:
                    continue
                xy = data.origin_xy+np.array([col, row])*resolution
                box = [math.nextafter(float(xy[0]), -math.inf), math.nextafter(float(xy[1]), -math.inf),
                       math.nextafter(float(xy[0]+resolution), math.inf), math.nextafter(float(xy[1]+resolution), math.inf)]
                if segment_box_intersection(a, b, box):
                    return False
        return True


def reference_distances(safe, start_xy, max_nodes):
    """Private bounded 8-neighbour Dijkstra, no diagonal corner cuts; no route export."""
    origin = safe.map.world_to_grid(start_xy)
    if safe.blocked[origin] or not safe.segment_safe(start_xy, safe.map.grid_to_world(*origin)):
        raise PlanningError("PLANNING_START_BLOCKED: 初态不在规范安全区域")
    distances = {origin: math.dist(start_xy, safe.map.grid_to_world(*origin))}
    queue = [(distances[origin], origin)]
    visited = 0
    h, w = safe.blocked.shape
    while queue:
        distance, (row, col) = heapq.heappop(queue)
        if distance != distances[row, col]:
            continue
        visited += 1
        if visited > max_nodes:
            raise PlanningError("PLANNING_NODE_LIMIT: 裁判搜索超过配置节点上限")
        for dy, dx in ((-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)):
            nr, nc = row+dy, col+dx
            if not (0 <= nr < h and 0 <= nc < w) or safe.blocked[nr, nc]:
                continue
            if dy and dx and (safe.blocked[row, nc] or safe.blocked[nr, col]):
                continue
            candidate = distance+safe.map.resolution_m*math.hypot(dy, dx)
            if candidate < distances.get((nr, nc), math.inf):
                distances[nr, nc] = candidate
                heapq.heappush(queue, (candidate, (nr, nc)))
    return distances


@dataclass(frozen=True)
class ResolvedPlanningTask:
    task_id: str
    definition_json: str

    def to_dict(self):
        return json.loads(self.definition_json)


def prepare_planning(config):
    level = config.get('campaign', {}).get('levels', {}).get(config.get('campaign', {}).get('active_level'))
    spec = level['rules'].get('global_planning') if level else None
    if spec is None:
        return None
    data, bounds = map_grid(config['scene']['walls'], spec['resolution_m'], spec['max_grid_cells'])
    body = config['body']
    radius = math.hypot(body['length_m'], body['width_m'])/2
    start = list(config['scene']['initial_pose'][:2])
    inputs = {'walls': config['scene']['walls'], 'body': body,
              'model': config['chassis_profiles'][config['scene']['default_chassis']], 'start_xy': start,
              'parameters': spec, 'seed': config['runtime']['seed']}
    if level['rules'].get('local_navigation'):
        inputs['local_navigation'] = level['rules']['local_navigation']
    identity = hashlib.sha256(canonical(inputs).encode()).hexdigest()
    safe = SafeGrid(data, radius, spec['safety_margin_m'])
    distances = reference_distances(safe, start, spec['max_search_nodes'])
    candidates = sorted((index, distance) for index, distance in distances.items()
                        if spec['min_reference_length_m'] <= distance <= spec['max_reference_length_m']
                        and math.dist(start, data.grid_to_world(*index)) >= spec['min_endpoint_distance_m'])
    random.Random(f"{config['runtime']['seed']}:global-planning").shuffle(candidates)
    for index, distance in candidates[:spec['max_goal_attempts']]:
        goal = data.grid_to_world(*index).tolist()
        if safe.segment_safe(start, goal):
            continue
        value = {'task_id': identity, 'seed': config['runtime']['seed'], 'frame_id': 'map',
                 'map': {'grid': data.grid.tolist(), 'origin_xy': data.origin_xy.tolist(),
                         'resolution_m': data.resolution_m, 'field_bounds_m': bounds,
                         'bounds_m': [*data.origin_xy.tolist(), *(data.origin_xy+np.array(data.grid.shape[::-1])*data.resolution_m).tolist()]},
                 'start_xy': start, 'goal_xy': goal, 'robot_radius_m': radius,
                 'safety_margin_m': spec['safety_margin_m'], 'inflation_cells': safe.cells,
                 'reference_length_m': distance}
        existing = config.get('navigation_planning')
        if existing is not None and canonical(existing) != canonical(value):
            raise PlanningError('PLANNING_TASK_MISMATCH: map/model/seed/parameters or task changed')
        config['navigation_planning'] = value
        config['observe_wall_contacts'] = True
        return ResolvedPlanningTask(identity, canonical(value))
    raise PlanningError('PLANNING_TASK_GENERATION_FAILED: 在配置上限内没有满足全部约束的终点')


def safe_task(task):
    m = task['map']
    return SafeGrid(OccupancyGrid(np.asarray(m['grid'], dtype=np.bool_), np.array(m['origin_xy']), m['resolution_m']),
                    task['robot_radius_m'], task['safety_margin_m'])


def validate_planned_path(value, task, spec):
    """Wire includes explicit dtype/shape. Never repair, resample or shrink obstacles."""
    if value is None:
        raise PlanningError('PLANNING_NO_PATH: 正式任务可达，但plan返回None（未找到路径）')
    if (not isinstance(value, dict) or set(value) != {'dtype', 'shape', 'points_m'}
            or value['dtype'] != 'float64'):
        raise PlanningError('PLANNING_PATH_DTYPE: 必须返回float64 NumPy数组')
    points = np.asarray(value['points_m'])
    if (points.dtype.kind not in 'fi' or points.ndim != 2 or points.shape[1] != 2
            or list(points.shape) != value['shape']):
        raise PlanningError('PLANNING_PATH_SHAPE: 必须为(N,2)地图系绝对坐标')
    if not 2 <= len(points) <= spec['max_path_points']:
        raise PlanningError('PLANNING_PATH_CAPACITY: 路径点数须为2至'+str(spec['max_path_points']))
    points = points.astype(np.float64)
    if not np.isfinite(points).all():
        raise PlanningError('PLANNING_PATH_FINITE: 路径包含NaN/Inf')
    tolerance = spec['endpoint_tolerance_m']
    for index, expected in ((0, task['start_xy']), (len(points)-1, task['goal_xy'])):
        if math.dist(points[index], expected) > tolerance:
            raise PlanningError(f'PLANNING_PATH_ENDPOINT: points[{index}]不匹配公开起终点')
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    invalid = np.flatnonzero((lengths <= spec['minimum_segment_m']) |
                             (lengths > spec['max_segment_m']+spec['spacing_tolerance_m']))
    if len(invalid):
        raise PlanningError(f'PLANNING_PATH_SPACING: segment[{invalid[0]}]间距不满足合同')
    safe = safe_task(task)
    for index, point in enumerate(points):
        if not safe.segment_safe(point, point):
            raise PlanningError(f'PLANNING_PATH_NODE_UNSAFE: points[{index}]越界或接触膨胀障碍')
    for index, (a, b) in enumerate(zip(points, points[1:])):
        if not safe.segment_safe(a, b):
            raise PlanningError(f'PLANNING_PATH_SEGMENT_UNSAFE: segment[{index}]进入或接触膨胀障碍')
    encoded = {'task_id': task['task_id'], 'points_m': points.tolist(), 'length_m': float(lengths.sum())}
    return {**encoded, 'path_id': hashlib.sha256(canonical(encoded).encode()).hexdigest()}
