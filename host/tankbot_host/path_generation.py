"""Bounded trusted path preparation, using the same resolved rectangular map as physics.

No player algorithms, world mutation, or level-ID dispatch belongs here. A conservative
orientation-independent chassis disc protects the complete rounded rectangle.
"""
from dataclasses import dataclass
import hashlib
import heapq
import json
import math
import random


class PathGenerationError(ValueError):
    pass


def canonical(value):
    # JSON passing through JavaScript normalizes 0.0 to 0. Preserve identity across
    # that representation-only change without quantizing any physical coordinate.
    def normalized(item):
        if isinstance(item,dict):return {k:normalized(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [normalized(v) for v in item]
        if type(item) is float and item.is_integer():return int(item)
        return item
    return json.dumps(normalized(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def distance_to_polyline(position, points):
    """Shortest Euclidean distance to all *segments*, including both end caps."""
    best = math.inf
    for a, b in zip(points, points[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length2 = dx*dx+dy*dy
        t = max(0., min(1., ((position[0]-a[0])*dx+(position[1]-a[1])*dy)/length2)) if length2 else 0.
        best = min(best, math.hypot(position[0]-a[0]-t*dx, position[1]-a[1]-t*dy))
    return best


def segment_box_intersection(a, b, box):
    low, high = 0., 1.
    for axis in range(2):
        delta = b[axis]-a[axis]
        if delta == 0:
            if a[axis] < box[axis] or a[axis] > box[axis+2]:
                return False
        else:
            t0, t1 = (box[axis]-a[axis])/delta, (box[axis+2]-a[axis])/delta
            low, high = max(low, min(t0, t1)), min(high, max(t0, t1))
            if low > high:
                return False
    return True


def wall_boxes(walls, inflation=0.):
    return [(w['center'][0]-w['size'][0]/2-inflation, w['center'][1]-w['size'][1]/2-inflation,
             w['center'][0]+w['size'][0]/2+inflation, w['center'][1]+w['size'][1]/2+inflation) for w in walls]


def segment_safe(a, b, boxes):
    # Expanded AABBs deliberately overapproximate the swept chassis disc, including
    # wall corners. All final segments are checked again after smoothing/resampling.
    return not any(segment_box_intersection(a, b, box) for box in boxes)


def length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def sample_arclength(points, spacing, tolerance, max_points=None):
    result = [list(points[0])]
    target, travelled = spacing, 0.
    for a, b in zip(points, points[1:]):
        span = math.dist(a, b)
        while target < travelled+span-tolerance:
            if max_points is not None and len(result)>=max_points-1:
                raise PathGenerationError('checkpoint capacity exceeded')
            t = (target-travelled)/span
            result.append([a[i]+t*(b[i]-a[i]) for i in range(2)])
            target += spacing
        travelled += span
    if math.dist(result[-1], points[-1]) > tolerance:
        result.append(list(points[-1]))
    else:
        result[-1] = list(points[-1])
    return result


def resample_polyline(points, spacing, tolerance, max_points=None):
    """Deliver a new polyline whose own arc-length intervals are exactly spacing.

    Circle/segment intersections march forward along the dense smoothing polyline;
    the delivered straight chords (not the discarded construction curve) define the
    reference. Its last segment may be shorter. Start and end are retained.
    """
    result = [list(points[0])]
    index = 0
    while index < len(points)-1:
        a, b, center = points[index], points[index+1], result[-1]
        if math.dist(b, center) < spacing-tolerance:
            index += 1
            continue
        dx, dy = b[0]-a[0], b[1]-a[1]
        ox, oy = a[0]-center[0], a[1]-center[1]
        aa = dx*dx+dy*dy
        if aa <= tolerance*tolerance:
            index += 1
            continue
        bb = 2*(ox*dx+oy*dy)
        discriminant = max(0., bb*bb-4*aa*(ox*ox+oy*oy-spacing*spacing))
        t = (-bb+math.sqrt(discriminant))/(2*aa)
        if t > 1+tolerance:
            index += 1
            continue
        point = [a[0]+min(1., t)*dx, a[1]+min(1., t)*dy]
        if max_points is not None and len(result)>=max_points-1:
            raise PathGenerationError('resampling capacity exceeded')
        result.append(point)
        if t >= 1-tolerance:
            index += 1
    if math.dist(result[-1], points[-1]) > tolerance:
        result.append(list(points[-1]))
    else:
        result[-1] = list(points[-1])
    return result


def shortcut(points, boxes):
    result, index = [points[0]], 0
    while index < len(points)-1:
        end = len(points)-1
        while end > index+1 and not segment_safe(points[index], points[end], boxes):
            end -= 1
        result.append(points[end]); index = end
    return result


def round_corners(points, radius, step, tolerance, max_points=None):
    corners = {}
    for index in range(1, len(points)-1):
        a, p, b = points[index-1:index+2]
        before, after = math.dist(a, p), math.dist(p, b)
        u = [(p[k]-a[k])/before for k in range(2)]
        v = [(b[k]-p[k])/after for k in range(2)]
        angle = math.acos(max(-1., min(1., sum(x*y for x, y in zip(u, v)))))
        if angle < tolerance:
            continue
        if angle >= math.pi-tolerance:
            raise PathGenerationError('reversal in search path')
        offset = radius*math.tan(angle/2)
        sign = 1 if u[0]*v[1]-u[1]*v[0] > 0 else -1
        entry = [p[k]-offset*u[k] for k in range(2)]
        exit_ = [p[k]+offset*v[k] for k in range(2)]
        center = [entry[0]-sign*radius*u[1], entry[1]+sign*radius*u[0]]
        corners[index] = (offset, entry, exit_, center, sign*angle)
    for index in range(len(points)-1):
        used = sum(corners[k][0] for k in (index, index+1) if k in corners)
        if used >= math.dist(points[index], points[index+1])-tolerance:
            raise PathGenerationError('insufficient segment length for configured smoothing radius')
    result = [list(points[0])]
    for index in range(1, len(points)-1):
        if index not in corners:
            continue
        _, entry, exit_, center, angle = corners[index]
        result.append(entry)
        start = math.atan2(entry[1]-center[1], entry[0]-center[0])
        count = math.ceil(abs(angle)*radius/step)
        if max_points is not None and len(result)+count+1>=max_points:
            raise PathGenerationError('smoothing capacity exceeded')
        for k in range(1, count):
            t = start+angle*k/count
            result.append([center[0]+radius*math.cos(t), center[1]+radius*math.sin(t)])
        result.append(exit_)
    result.append(list(points[-1]))
    return result


def self_intersects(points, tolerance):
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a, b, c):
        return abs(cross(a, b, c)) <= tolerance and all(min(a[k], b[k])-tolerance <= c[k] <= max(a[k], b[k])+tolerance for k in range(2))
    for i, (a, b) in enumerate(zip(points, points[1:])):
        for j in range(i+2, len(points)-1):
            c, d = points[j:j+2]
            if any(max(a[k], b[k])+tolerance < min(c[k], d[k]) or max(c[k], d[k])+tolerance < min(a[k], b[k]) for k in range(2)):
                continue
            if (cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b):
                return True
    return False


def validate_path(points, walls, body, start, parameters):
    p, tol = parameters, parameters['numeric_tolerance_m']
    if not 2 <= len(points) <= p['max_path_points'] or any(len(row) != 2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row) for row in points):
        raise PathGenerationError('invalid finite (N,2) reference')
    if math.dist(points[0], start[:2]) > tol:
        raise PathGenerationError('reference start mismatch')
    spans = [math.dist(a,b) for a,b in zip(points,points[1:])]
    if any(abs(span-p['sample_spacing_m']) > tol for span in spans[:-1]) or not tol < spans[-1] <= p['sample_spacing_m']+tol:
        raise PathGenerationError('reference arc-length spacing mismatch')
    radius = math.hypot(body['length_m'],body['width_m'])/2+p['safety_margin_m']
    boxes = wall_boxes(walls,radius)
    if not all(segment_safe(a,b,boxes) for a,b in zip(points,points[1:])):
        raise PathGenerationError('unsafe final swept chassis corridor')
    total, direct = sum(spans), math.dist(points[0],points[-1])
    if not p['min_length_m'] <= total <= p['max_length_m'] or direct < p['min_endpoint_distance_m']:
        raise PathGenerationError('final length/endpoint distance outside constraints')
    if p['require_blocked_chord'] and segment_safe(points[0],points[-1],boxes):
        raise PathGenerationError('reference does not go around an obstacle')
    if total-direct < p['min_detour_m'] or self_intersects(points,tol):
        raise PathGenerationError('insufficient detour or self intersection')
    turn = 0.
    for a,b,c in zip(points,points[1:],points[2:]):
        ab,bc,ac = math.dist(a,b),math.dist(b,c),math.dist(a,c)
        cross = abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
        angle = math.acos(max(-1.,min(1.,sum((b[k]-a[k])*(c[k]-b[k]) for k in range(2))/(ab*bc))))
        turn += angle
        if angle > p['max_turn_angle_rad'] or (cross > tol and ab*bc*ac/(2*cross) < p['min_turn_radius_m']):
            raise PathGenerationError('unexecutable final turn')
    if turn < p['min_total_turn_rad']:
        raise PathGenerationError('reference has insufficient turning')
    return {'length_m':total,'endpoint_distance_m':direct,'total_turn_rad':turn,'clearance_radius_m':radius}


@dataclass(frozen=True)
class ResolvedPath:
    identity: str
    definition_json: str

    def to_dict(self):
        return json.loads(self.definition_json)


def generation_inputs(walls,body,start,parameters,seed,checkpoint_spacing_m):
    return {'generator':'warehouse_search_round_v1','walls':walls,
            'body_size_m':[body['length_m'],body['width_m']], 'initial_pose':list(start),
            'parameters':parameters,'seed':seed,'checkpoint_spacing_m':checkpoint_spacing_m}


def generate_path(walls, body, start, parameters, seed, checkpoint_spacing_m):
    p, tol = parameters, parameters['numeric_tolerance_m']
    if not walls:
        raise PathGenerationError('PATH_GENERATION_FAILED: bounded map geometry is required')
    radius = math.hypot(body['length_m'],body['width_m'])/2
    search_boxes = wall_boxes(walls,radius+p['planning_margin_m'])
    if not segment_safe(start[:2],start[:2],search_boxes):
        raise PathGenerationError('PATH_SPAWN_BLOCKED: complete chassis and planning margin overlap a wall')
    boxes = wall_boxes(walls)
    bounds = [min(b[axis] for b in boxes) for axis in range(2)]+[max(b[axis+2] for b in boxes) for axis in range(2)]
    step = p['grid_resolution_m']
    nx,ny = (math.ceil((bounds[k+2]-bounds[k])/step)+1 for k in range(2))
    if nx*ny > p['max_grid_nodes']:
        raise PathGenerationError('PATH_GRID_LIMIT: map/grid exceeds configured node bound')
    def xy(cell):
        return [bounds[k]+cell[k]*step for k in range(2)]
    free = {(x,y) for x in range(nx) for y in range(ny) if segment_safe(xy((x,y)),xy((x,y)),search_boxes)}
    origin = tuple(round((start[k]-bounds[k])/step) for k in range(2))
    if origin not in free or not segment_safe(start[:2],xy(origin),search_boxes):
        raise PathGenerationError('PATH_SPAWN_GRID_BLOCKED')
    costs,parents,queue = {origin:0.},{origin:None},[(0.,origin)]
    directions = [(x,y) for x in (-1,0,1) for y in (-1,0,1) if x or y]
    expansions = 0
    while queue:
        cost,cell = heapq.heappop(queue)
        if cost != costs[cell]:
            continue
        expansions += 1
        if expansions > p['max_search_expansions']:
            raise PathGenerationError('PATH_SEARCH_LIMIT: bounded search exhausted')
        for dx,dy in directions:
            other = (cell[0]+dx,cell[1]+dy)
            if other not in free or (dx and dy and ((cell[0]+dx,cell[1]) not in free or (cell[0],cell[1]+dy) not in free)):
                continue
            candidate = cost+step*math.hypot(dx,dy)
            if candidate < costs.get(other,math.inf):
                costs[other],parents[other] = candidate,cell
                heapq.heappush(queue,(candidate,other))
    candidates = sorted(cell for cell,cost in costs.items() if cost >= p['min_length_m'] and math.dist(start[:2],xy(cell)) >= p['min_endpoint_distance_m'])
    random.Random(seed).shuffle(candidates)  # Independent from every sensor random stream.
    reasons = {}
    for attempt,cell in enumerate(candidates[:p['max_attempts']],1):
        chain = []
        while cell is not None:
            chain.append(xy(cell)); cell = parents[cell]
        chain.reverse()
        if math.dist(start[:2],chain[0]) <= tol:
            chain[0] = list(start[:2])
        else:
            chain.insert(0,list(start[:2]))
        try:
            simplified = shortcut(chain,search_boxes)
            smooth = round_corners(simplified,p['smoothing_radius_m'],p['smoothing_step_m'],tol,p['max_smoothing_points'])
            points = resample_polyline(smooth,p['sample_spacing_m'],tol,p['max_path_points'])
            stats = validate_path(points,walls,body,start,p)
            checkpoints = sample_arclength(points,checkpoint_spacing_m,tol,p['max_path_points'])
        except PathGenerationError as error:
            reasons[str(error)] = reasons.get(str(error),0)+1
            continue
        inputs = generation_inputs(walls,body,start,p,seed,checkpoint_spacing_m)
        input_sha = hashlib.sha256(canonical(inputs).encode()).hexdigest()
        value = {'reference_version':'1.0','frame_id':'map','points_m':points,
                 'checkpoints_m':checkpoints,
                 'parameters':p,'seed':seed,'input_sha256':input_sha,**stats,'attempts':attempt}
        identity = hashlib.sha256(canonical(value).encode()).hexdigest()
        value['path_id'] = identity
        return ResolvedPath(identity,canonical(value))
    raise PathGenerationError('PATH_GENERATION_FAILED: no valid final path within '+str(p['max_attempts'])+' attempts; '+canonical(reasons))


def prepare_path(config):
    """Resolve or verify a frozen reference before creating Core/Worker instances."""
    active = config.get('campaign',{}).get('active_level')
    level = config.get('campaign',{}).get('levels',{}).get(active)
    spec = level['rules'].get('path_tracking') if level else None
    if not spec:
        return None
    walls,body,start = config['scene']['walls'],config['body'],config['scene']['initial_pose']
    p,seed = spec['generation'],config['runtime']['seed']
    expected = hashlib.sha256(canonical(generation_inputs(walls,body,start,p,seed,spec['checkpoint_spacing_m'])).encode()).hexdigest()
    existing = config.get('navigation_path')
    if existing is None:
        reference = generate_path(walls,body,start,p,seed,spec['checkpoint_spacing_m'])
    else:
        from tankbot_protocol.validation import Validator
        Validator(config,'path-preparation').structure(existing,'path-tracking.schema.json')
        value = {k:v for k,v in existing.items() if k != 'path_id'}
        if (existing['input_sha256'] != expected or existing['seed'] != seed or canonical(existing['parameters']) != canonical(p)
                or hashlib.sha256(canonical(value).encode()).hexdigest() != existing['path_id']):
            raise PathGenerationError('PATH_REFERENCE_MISMATCH: map/model/seed/parameters or reference changed')
        stats = validate_path(existing['points_m'],walls,body,start,p)
        if any(abs(stats[k]-existing[k]) > p['numeric_tolerance_m'] for k in stats):
            raise PathGenerationError('PATH_REFERENCE_METRIC_MISMATCH')
        checkpoints = sample_arclength(existing['points_m'],spec['checkpoint_spacing_m'],p['numeric_tolerance_m'],p['max_path_points'])
        if checkpoints != existing['checkpoints_m']:
            raise PathGenerationError('PATH_CHECKPOINT_MISMATCH')
        reference = ResolvedPath(existing['path_id'],canonical(existing))
    config['navigation_path'] = reference.to_dict()
    config['observe_wall_contacts'] = True
    return reference
