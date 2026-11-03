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
    return files
