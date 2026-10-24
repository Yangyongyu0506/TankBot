"""Acceptance-only solutions and a sensor/estimate-driven manual-control harness."""
import math

COORDINATES = '''from tankbot import TargetEstimate
import math
def to_map(detection, own_pose):
    angle = own_pose.yaw_rad + detection.bearing_rad
    return TargetEstimate(own_pose.x_m + detection.range_m*math.cos(angle),
                          own_pose.y_m + detection.range_m*math.sin(angle))
'''

TRANSFORMS = '''import math
import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D
def radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:
    c: float = math.cos(own_pose.yaw_rad)
    s: float = math.sin(own_pose.yaw_rad)
    T_map_radar: NDArray[np.float64] = np.array([
        [c, -s, 0.0, own_pose.x_m],
        [s, c, 0.0, own_pose.y_m],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float64)
    return T_map_radar
'''

EMA = '''from tankbot import TargetEstimate
class Tracker:
    def __init__(self) -> None: self.point: TargetEstimate | None = None
    def update(self, measurements: tuple[TargetEstimate, ...], dt: float) -> TargetEstimate | None:
        if measurements:
            p: TargetEstimate = measurements[0]
            self.point = p if self.point is None else TargetEstimate(
                self.point.x_m + .45*(p.x_m-self.point.x_m),
                self.point.y_m + .45*(p.y_m-self.point.y_m))
        return self.point
'''

WINDOW = '''from collections import deque
from tankbot import TargetEstimate
class Tracker:
    def __init__(self) -> None: self.points: deque[TargetEstimate] = deque(maxlen=3)
    def update(self, measurements: tuple[TargetEstimate, ...], dt: float) -> TargetEstimate | None:
        if measurements: self.points.append(measurements[0])
        return TargetEstimate(sum(p.x_m for p in self.points)/len(self.points),
                              sum(p.y_m for p in self.points)/len(self.points)) if self.points else None
'''


def solutions(config, tracker=EMA):
    from tankbot_host.workspace import starter
    sources = starter(config)
    if config['campaign']['active_level'] != 'c0':
        sources['perception/transforms.py'] = TRANSFORMS
    if config['campaign']['active_level'] == 'c2':
        sources['perception/tracker.py'] = tracker
    return sources


class AimHarness:
    """Only published target estimates, authorized self/turret pose and known gun speed."""
    def __init__(self):
        self.samples = []

    def step(self, authority):
        estimate = authority._target_estimate
        if estimate is None:
            return
        tick, point = estimate['simulation_tick'], estimate['payload']
        if not self.samples or self.samples[-1][0] != tick:
            self.samples.append((tick, point))
            self.samples = [p for p in self.samples if tick-p[0] <= authority.hz]
        vx = vy = 0.0
        if len(self.samples) > 1:
            first_tick, first = self.samples[0]
            dt = (tick-first_tick)/authority.hz
            vx = (point['x_m']-first['x_m'])/dt
            vy = (point['y_m']-first['y_m'])/dt
        pose = authority._sensors['/robot/localization/pose']['payload']
        x, y = point['x_m']-pose['x_m'], point['y_m']-pose['y_m']
        lead = math.hypot(x,y)/authority.config['weapons']['projectile']['relative_speed_mps'] + (authority.tick-tick)/authority.hz
        desired = math.atan2(y+vy*lead, x+vx*lead)
        turret = authority._sensors['/robot/turret/joint_states']['payload']['position'][0]
        error = (desired-pose['yaw_rad']-turret+math.pi)%math.tau-math.pi
        authority.turret_keyboard({'velocity_radps':max(-2.0,min(2.0,4*error))})
        if abs(error) < .06 and authority._sensors['/robot/weapons/cannon/state']['payload']['ready']:
            authority.fire_keyboard({'request_id':f'aim-{authority.tick}'})
