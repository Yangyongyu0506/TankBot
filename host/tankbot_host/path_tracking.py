"""Private continuous-path judge. Public projections require separate task grants."""
import copy
import math
import numpy as np


class PathTracking:
    kind = 'path_tracking'

    def __init__(self, specification, reference, parameters, physics_hz):
        self.spec = copy.deepcopy({**specification, **parameters})
        self.reference = copy.deepcopy(reference)
        self.hz = physics_hz
        self.checkpoints = reference['checkpoints_m']
        points = np.asarray(reference['points_m'], dtype=np.float64)
        self.segment_starts = points[:-1]
        self.segment_deltas = np.diff(points, axis=0)
        self.segment_squared = np.sum(self.segment_deltas**2, axis=1)
        self.goal_index = self.reached_count = self.settled_ticks = 0
        self.complete = self.collision = self.deviation_exceeded = False
        self.stable_since = self.last_tick = None
        self.weighted_squared_error = self.scored_duration_s = 0.
        self.max_deviation_m = 0.
        self.tracking_samples = 0
        self.goal_distance_m = math.dist(reference['points_m'][0], reference['points_m'][-1])

    def start(self, tick):
        if self.last_tick is None:
            self.last_tick = tick

    def observe(self, pose, velocity, tick, wall_contact=False):
        if self.complete or (self.last_tick is not None and tick <= self.last_tick):
            return
        previous = self.last_tick
        if previous is not None and tick != previous+1:
            self.stable_since = None
        self.last_tick = tick
        dt = (tick-previous)/self.hz if previous is not None else 1/self.hz
        delta = np.asarray(pose[:2], dtype=np.float64)-self.segment_starts
        projection = np.clip(np.sum(delta*self.segment_deltas,axis=1)/self.segment_squared,0.,1.)
        distance = float(np.min(np.linalg.norm(delta-projection[:,None]*self.segment_deltas,axis=1)))
        self.weighted_squared_error += distance*distance*dt
        self.scored_duration_s += dt
        self.tracking_samples += 1
        self.max_deviation_m = max(self.max_deviation_m,distance)
        self.deviation_exceeded |= distance > self.spec['max_deviation_m']
        self.collision |= wall_contact
        self.goal_distance_m = math.dist(pose[:2],self.reference['points_m'][-1])
        if self.reached_count < len(self.checkpoints) and math.dist(pose[:2],self.checkpoints[self.reached_count]) <= self.spec['checkpoint_radius_m']:
            self.reached_count += 1  # No loop: one checkpoint at most per physics tick.
            self.goal_index = min(self.reached_count,len(self.checkpoints)-1)
        stopped = (self.reached_count == len(self.checkpoints)
                   and self.goal_distance_m <= self.spec['position_tolerance_m']
                   and math.hypot(velocity[0],velocity[1]) <= self.spec['stop_linear_speed_mps']
                   and abs(velocity[2]) <= self.spec['stop_yaw_rate_radps'])
        if not stopped:
            self.stable_since = None
            self.settled_ticks = 0
        else:
            if self.stable_since is None:
                self.stable_since = tick
            self.settled_ticks = tick-self.stable_since
            self.complete = self.settled_ticks >= self.spec['stop_duration_ticks']

    @property
    def rmse_m(self):
        return math.sqrt(self.weighted_squared_error/self.scored_duration_s) if self.scored_duration_s else None

    def facts(self):
        return {'path_complete':self.complete,'path_collision':self.collision,
                'path_deviation_exceeded':self.deviation_exceeded,
                'tracking_rmse_m':self.rmse_m if self.rmse_m is not None else math.inf,
                'max_deviation_m':self.max_deviation_m}

    def phase(self):
        return {'cycle_index':0,'segment_index':self.goal_index,'label':f'检查点 {self.goal_index+1}'}

    def public(self):
        return {'path_id':self.reference['path_id'],'goal_index':self.goal_index,
                'reached_count':self.reached_count,'total':len(self.checkpoints),
                'settled_ticks':self.settled_ticks,'required_settle_ticks':self.spec['stop_duration_ticks'],
                'complete':self.complete}

    def report(self):
        return {'tracking_rmse_m':self.rmse_m,'max_deviation_m':self.max_deviation_m,
                'scored_duration_s':self.scored_duration_s,'tracking_samples':self.tracking_samples}
