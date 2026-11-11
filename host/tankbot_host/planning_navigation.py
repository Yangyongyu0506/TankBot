"""Known-map navigation judge: reach/settle and contact, with terminal-only path metrics."""
import copy
import math
from .path_tracking import PolylineMetrics


class PlanningNavigation(PolylineMetrics):
    kind = 'global_planning'

    def __init__(self, specification, task, physics_hz):
        self.spec = copy.deepcopy(specification)
        self.task = copy.deepcopy(task)
        self.hz = physics_hz
        self.reference = None
        self.complete = self.collision = False
        self.stable_since = self.last_tick = None
        self.settled_ticks = 0
        self.goal_distance_m = math.dist(task['start_xy'], task['goal_xy'])
        self.path_length_m = 0.
        self.preparation = {'phase': 'waiting', 'planning_elapsed_ms': None}

    def accept_path(self, reference, planning_elapsed_ms):
        if self.reference is not None:
            raise ValueError('PLANNING_PATH_FROZEN: 本次尝试的路径已经冻结，请重试')
        self.reference = copy.deepcopy(reference)
        self.init_polyline(reference['points_m'])
        self.preparation = {'phase': 'ready', 'planning_elapsed_ms': planning_elapsed_ms}

    def start(self, tick):
        if self.last_tick is None:
            self.last_tick = tick

    def observe(self, pose, velocity, tick, wall_contact=False):
        if self.reference is None or self.complete or (self.last_tick is not None and tick <= self.last_tick):
            return
        previous = self.last_tick
        if previous is not None and tick != previous+1:
            self.stable_since = None
        self.last_tick = tick
        self.observe_error(pose, (tick-previous)/self.hz if previous is not None else 1/self.hz)
        self.collision |= wall_contact
        self.goal_distance_m = math.dist(pose[:2], self.task['goal_xy'])
        stopped = (self.goal_distance_m <= self.spec['position_tolerance_m']
                   and math.hypot(velocity[0], velocity[1]) <= self.spec['stop_linear_speed_mps']
                   and abs(velocity[2]) <= self.spec['stop_yaw_rate_radps'])
        if not stopped:
            self.stable_since = None
            self.settled_ticks = 0
        else:
            if self.stable_since is None:
                self.stable_since = tick
            self.settled_ticks = tick-self.stable_since
            self.complete = self.settled_ticks >= self.spec['stop_duration_ticks']

    def facts(self):
        return {'planning_complete': self.complete, 'planning_collision': self.collision}

    def phase(self):
        return {'cycle_index': 0, 'segment_index': 0, 'label': '前往公开终点'}

    def report(self):
        metrics = super().report() if self.reference is not None else {
            'tracking_rmse_m': None, 'max_deviation_m': None, 'scored_duration_s': 0., 'tracking_samples': 0}
        return {**metrics, 'path_length_m': self.path_length_m}

    def public(self, permission, layers):
        state = {'task_id': self.task['task_id'], 'phase': self.preparation['phase']}
        live = permission.get('live', [])
        if 'goal_distance_m' in live:
            state.update(goal_distance_m=self.goal_distance_m, settled_ticks=self.settled_ticks,
                         required_settle_ticks=self.spec['stop_duration_ticks'])
        if 'planning_elapsed_ms' in live:
            state['planning_elapsed_ms'] = self.preparation['planning_elapsed_ms']
        if self.reference is not None:
            if 'planned_length_m' in live:
                state['planned_length_m'] = self.reference['length_m']
            if 'path' in layers:
                state['route'] = copy.deepcopy(self.reference)
        if self.preparation.get('error'):
            state['error'] = self.preparation['error']
        return state
