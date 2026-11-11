"""Trusted instantaneous ray/AABB sensing against complete private physical geometry."""
import copy
import json
import math
import random
import time
from collections import deque
import numpy as np


class DistanceScanSimulator:
    def __init__(self, instance, walls, history_limit):
        self.parameters = json.loads(instance.parameters_json)
        p = self.parameters
        self.angles = p['angle_min_rad']+np.arange(p['ray_count'])*p['angle_increment_rad']
        self.boxes = np.asarray([[w['center'][0]-w['size'][0]/2, w['center'][1]-w['size'][1]/2,
                                  w['center'][0]+w['size'][0]/2, w['center'][1]+w['size'][1]/2] for w in walls])
        self.costs_ms = deque(maxlen=history_limit)
        self.closed = False

    def reset(self, seed):
        if self.closed:
            raise ValueError('SCAN_CLOSED')
        self.random = random.Random(seed)
        self.last_tick = None
        self.cached = None
        self.costs_ms.clear()

    def measure(self, private, tick):
        if self.closed:
            raise ValueError('SCAN_CLOSED')
        if tick == self.last_tick:
            return copy.deepcopy(self.cached)
        started = time.perf_counter()
        x, y, yaw = private['truth_pose']
        directions = np.column_stack((np.cos(self.angles+yaw), np.sin(self.angles+yaw)))
        # Slab intersections: broadcast rays x walls x axes. Parallel rays
        # inside a slab leave its interval unbounded; outside slabs miss.
        low = self.boxes[None, :, :2]-np.array([x, y])
        high = self.boxes[None, :, 2:]-np.array([x, y])
        d = directions[:, None, :]
        parallel = np.abs(d) < np.finfo(float).eps
        with np.errstate(divide='ignore', invalid='ignore'):
            t0, t1 = low/d, high/d
        near = np.where(parallel, -np.inf, np.minimum(t0, t1)).max(axis=2)
        far = np.where(parallel, np.inf, np.maximum(t0, t1)).min(axis=2)
        outside = (parallel & ((low > 0) | (high < 0))).any(axis=2)
        valid = ~outside & (far >= np.maximum(near, 0))
        distances = np.where(valid, np.maximum(near, 0), np.inf).min(axis=1)
        p = self.parameters
        hit = distances <= p['range_max_m']
        # JSON crossing JS can turn 6.0 into the integer 6. Explicit float64
        # prevents noisy returns being truncated (and near returns becoming 0).
        ranges = np.full(len(self.angles), p['range_max_m'], dtype=np.float64)
        for index in np.flatnonzero(hit):
            noisy = distances[index]+self.random.gauss(0, p['noise_stddev_m'])
            ranges[index] = p['range_min_m'] if distances[index] < p['range_min_m'] else min(p['range_max_m'], max(p['range_min_m'], noisy))
        self.cached = {'ranges_m': ranges.tolist(), 'hit_mask': hit.tolist(), 'sample_tick': tick,
                       **{key: p[key] for key in ('angle_min_rad', 'angle_increment_rad', 'range_min_m', 'range_max_m', 'noise_stddev_m')}}
        self.last_tick = tick
        self.costs_ms.append((time.perf_counter()-started)*1000)
        return copy.deepcopy(self.cached)

    def close(self):
        self.closed = True
        self.cached = None
