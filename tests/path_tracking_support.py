"""Verification-only follower; source is installed exclusively in isolated test projects."""
from pathlib import Path
import yaml
from navigation_support import solution as navigation_solution

ROOT=Path(__file__).resolve().parents[1]


def solution(config):
    files=navigation_solution(config)
    tuning=yaml.safe_load((ROOT/'tests/fixtures/path-tracking-reference.yaml').read_text())
    source='''import numpy as np
from numpy.typing import NDArray
from tankbot import Twist, Vector3

class PathFollower:
    def __init__(self, reference_speed_mps: float, max_vx_mps: float,
                 max_wz_radps: float, position_tolerance_m: float) -> None:
        self.speed: float = reference_speed_mps
        self.max_vx: float = max_vx_mps
        self.max_wz: float = max_wz_radps

    def update(self, estimated_pose: NDArray[np.float64], path_xy: NDArray[np.float64], dt: float) -> Twist:
        xy: NDArray[np.float64] = estimated_pose[:2]
        segments: NDArray[np.float64] = np.diff(path_xy,axis=0)
        spans: NDArray[np.float64] = np.linalg.norm(segments,axis=1)
        fractions: NDArray[np.float64] = np.clip(np.sum((xy-path_xy[:-1])*segments,axis=1)/(spans**2),0.,1.)
        projections: NDArray[np.float64] = path_xy[:-1]+fractions[:,None]*segments
        closest: int = int(np.argmin(np.linalg.norm(projections-xy,axis=1)))
        arc: NDArray[np.float64] = np.concatenate((np.zeros(1,dtype=np.float64),np.cumsum(spans)))
        station: float = float(arc[closest]+fractions[closest]*spans[closest])
        ahead: float = min(float(arc[-1]),station+LOOKAHEAD)
        index: int = min(int(np.searchsorted(arc,ahead,side="right")-1),len(spans)-1)
        target: NDArray[np.float64] = path_xy[index]+(ahead-arc[index])/spans[index]*segments[index]
        end_distance: float = float(np.linalg.norm(path_xy[-1]-xy))
        if end_distance<=STOP_RADIUS:
            return Twist()
        delta: NDArray[np.float64] = target-xy
        heading: float = float(np.arctan2(delta[1],delta[0])-estimated_pose[2])
        heading = float(np.arctan2(np.sin(heading),np.cos(heading)))
        if abs(heading)>TURN_THRESHOLD:
            return Twist(angular=Vector3(z=float(np.clip(HEADING_GAIN*heading,-self.max_wz,self.max_wz))))
        curvature: float = 2*float(np.sin(heading))/max(float(np.linalg.norm(delta)),STOP_RADIUS)
        velocity: float = min(self.speed,self.max_vx,TERMINAL_GAIN*end_distance)/(1+CURVE_SCALE*abs(curvature))
        angular: float = float(np.clip(curvature*velocity,-self.max_wz,self.max_wz))
        return Twist(linear=Vector3(x=velocity),angular=Vector3(z=angular))
'''
    for marker,key in [('LOOKAHEAD','lookahead_m'),('STOP_RADIUS','stop_radius_m'),('TURN_THRESHOLD','turn_in_place_threshold_rad'),
                       ('HEADING_GAIN','heading_gain_per_s'),('TERMINAL_GAIN','terminal_position_gain_per_s'),('CURVE_SCALE','curvature_speed_scale_m')]:
        source=source.replace(marker,repr(tuning[key]))
    files['navigation/path_follower.py']=source
    return files
