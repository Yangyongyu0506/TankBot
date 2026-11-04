"""Trusted test controller; never installed into the player's persistent workspace."""
from tankbot_host.workspace import starter


def solution(config):
    files=starter(config)
    kp=config["validation"]["reference_drive"]["voltage_kp"]
    files["control/wheel_controller.py"]='''import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters, Twist

class WheelController:
    def __init__(self, model: DifferentialDriveParameters) -> None:
        self.model: DifferentialDriveParameters = model

    def control(self, target: Twist, wheel_rates_radps: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        m: DifferentialDriveParameters = self.model
        v: float = target.linear.x
        w: float = target.angular.z
        desired: NDArray[np.float64] = np.array([v-w*m.wheel_separation_m/2, v+w*m.wheel_separation_m/2], dtype=np.float64)/m.wheel_radius_m
        force: float = m.drag_x_n_s_per_m*v
        yaw_torque: float = m.drag_yaw_nm_s*w
        load: NDArray[np.float64] = m.wheel_radius_m/2*np.array([force-2*yaw_torque/m.wheel_separation_m, force+2*yaw_torque/m.wheel_separation_m], dtype=np.float64)
        feedforward: NDArray[np.float64] = m.back_emf_v_s_per_rad*desired+m.resistance_ohm/m.torque_constant_nm_per_a*load
        return np.asarray(feedforward+KP*(desired-wheel_rates_radps), dtype=np.float64)
'''.replace('KP',repr(kp))
    if config["campaign"]["levels"][config["campaign"]["active_level"]]["evaluation"].get("source")=="player_pose":
        files['localization/odometry.py']='''import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters

class Odometry:
    def __init__(self, model: DifferentialDriveParameters, initial_pose: NDArray[np.float64]) -> None:
        self.model: DifferentialDriveParameters = model
        self.pose: NDArray[np.float64] = initial_pose.copy()

    def update(self, wheel_rates_radps: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        velocity: float = self.model.wheel_radius_m*float(np.sum(wheel_rates_radps))/2
        angular: float = self.model.wheel_radius_m*float(wheel_rates_radps[1]-wheel_rates_radps[0])/self.model.wheel_separation_m
        middle: float = self.pose[2]+angular*dt/2
        self.pose += np.array([velocity*np.cos(middle),velocity*np.sin(middle),angular],dtype=np.float64)*dt
        return self.pose.copy()
'''
    if 'ekf_localization' in config['campaign']['levels'][config['campaign']['active_level']]['scaffolding']['components']:
        files['localization/ekf.py']=ekf_solution(config)
    if 'waypoint_controller' in config['campaign']['levels'][config['campaign']['active_level']]['scaffolding']['components']:
        files['navigation/waypoint_controller.py']=waypoint_solution(config)
    return files


def waypoint_solution(config):
    """Verification controller kept out of generated/player projects."""
    tuning=config['validation']['reference_navigation']
    source='''import numpy as np
from numpy.typing import NDArray
from tankbot import Twist, Vector3

class WaypointController:
    def __init__(self, position_tolerance_m: float, max_vx_mps: float, max_wz_radps: float) -> None:
        self.stop_radius_m: float = position_tolerance_m*STOP_FRACTION
        self.max_vx_mps: float = max_vx_mps
        self.max_wz_radps: float = max_wz_radps

    def update(self, estimated_pose: NDArray[np.float64], target_xy: NDArray[np.float64], dt: float) -> Twist:
        delta: NDArray[np.float64] = target_xy-estimated_pose[:2]
        distance: float = float(np.linalg.norm(delta))
        if distance<=self.stop_radius_m:
            return Twist()
        desired: float = float(np.arctan2(delta[1],delta[0]))
        error: float = desired-float(estimated_pose[2])
        error = float(np.arctan2(np.sin(error),np.cos(error)))
        velocity: float = min(self.max_vx_mps,POSITION_GAIN*distance)*max(0.,float(np.cos(error)))
        if abs(error)>TURN_THRESHOLD:
            velocity = 0.
        turn: float = float(np.clip(HEADING_GAIN*error,-self.max_wz_radps,self.max_wz_radps))
        return Twist(linear=Vector3(x=velocity),angular=Vector3(z=turn))
'''
    for marker,key in [('STOP_FRACTION','stop_radius_fraction'),('POSITION_GAIN','position_gain_per_s'),
                       ('TURN_THRESHOLD','turn_in_place_threshold_rad'),('HEADING_GAIN','heading_gain_per_s')]:
        source=source.replace(marker,repr(tuning[key]))
    return source


def ekf_solution(config):
    """Trusted verification reference, never generated in a player workspace."""
    tuning=config['validation']['reference_localization']
    return '''import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters

class EkfLocalization:
    def __init__(self, model: DifferentialDriveParameters, initial_pose: NDArray[np.float64],
                 initial_covariance: NDArray[np.float64], wheel_rate_covariance: NDArray[np.float64],
                 gain_error_bounds: NDArray[np.float64]) -> None:
        self.model: DifferentialDriveParameters = model
        self.state: NDArray[np.float64] = initial_pose.copy()
        self.covariance: NDArray[np.float64] = initial_covariance.copy()
        self.wheel_rate_covariance: NDArray[np.float64] = wheel_rate_covariance
        self.gain_variance: float = float(np.diff(gain_error_bounds)[0]**2/12)

    def predict(self, wheel_rates_radps: NDArray[np.float64], dt: float) -> None:
        r: float = self.model.wheel_radius_m
        b: float = self.model.wheel_separation_m
        d: float = r*float(np.sum(wheel_rates_radps))*dt/2
        a: float = r*float(wheel_rates_radps[1]-wheel_rates_radps[0])*dt/b
        h: float = self.state[2]+a/2
        c: float = float(np.cos(h))
        s: float = float(np.sin(h))
        f: NDArray[np.float64] = np.array([[1.,0.,-d*s],[0.,1.,d*c],[0.,0.,1.]],dtype=np.float64)
        g: NDArray[np.float64] = np.array([
            [r*dt*c/2+d*s*r*dt/(2*b),r*dt*c/2-d*s*r*dt/(2*b)],
            [r*dt*s/2-d*c*r*dt/(2*b),r*dt*s/2+d*c*r*dt/(2*b)],[-r*dt/b,r*dt/b]],dtype=np.float64)
        q: NDArray[np.float64] = self.wheel_rate_covariance+np.diag(wheel_rates_radps**2*self.gain_variance)
        self.state += np.array([d*c,d*s,a],dtype=np.float64)
        self.covariance = f@self.covariance@f.T+g@q@g.T+np.diag([POS_STD**2,POS_STD**2,YAW_STD**2])*dt

    def correct(self, position_m: NDArray[np.float64], measurement_covariance: NDArray[np.float64]) -> None:
        h: NDArray[np.float64] = np.array([[1.,0.,0.],[0.,1.,0.]],dtype=np.float64)
        gain: NDArray[np.float64] = np.linalg.solve(h@self.covariance@h.T+measurement_covariance,h@self.covariance).T
        self.state += gain@(position_m-h@self.state)
        residual: NDArray[np.float64] = np.eye(3,dtype=np.float64)-gain@h
        self.covariance = residual@self.covariance@residual.T+gain@measurement_covariance@gain.T
'''.replace('POS_STD',repr(tuning['position_process_std_m_per_sqrt_s'])).replace('YAW_STD',repr(tuning['yaw_process_std_rad_per_sqrt_s']))
