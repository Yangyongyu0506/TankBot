"""系统管理：同模块名义跟踪与局部控制，缺测时主动发布零参考。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import (DifferentialDriveParameters, Inputs, LocalControlFeedback,
                     LocalControlInput, Module, ModuleContext, Pose2D, Scan2D,
                     Twist, Vector3, readonly_path)
from navigation.path_follower import PathFollower
from navigation.local_controller import LocalController


def checked_command(command: Twist, limits: dict) -> Twist:
    if not isinstance(command, Twist) or not isinstance(command.linear, Vector3) or not isinstance(command.angular, Vector3):
        raise TypeError("导航控制器必须返回Twist，linear/angular须为Vector3")
    values: list[float] = [command.linear.x, command.linear.y, command.linear.z,
                           command.angular.x, command.angular.y, command.angular.z]
    if any(isinstance(value, bool) or not isinstance(value, (int,float,np.integer,np.floating)) for value in values):
        raise TypeError("Twist各分量必须为实数，不能为字符串或布尔值")
    if not np.isfinite(values).all() or any(values[index] != 0 for index in (1,2,3,4)):
        raise ValueError("Twist须为有限平面差速指令，仅linear.x/angular.z非零")
    if command.linear.x < limits['min_vx_mps']:
        raise ValueError("禁止主动倒车：linear.x必须非负")
    return Twist(Vector3(x=float(min(command.linear.x, limits['max_vx_mps']))),
                 Vector3(z=float(np.clip(command.angular.z, -limits['max_wz_radps'], limits['max_wz_radps']))))


class LocalNavigationModule(Module):
    scaffold_api: str = "local_navigation@1"

    def setup(self, ctx: ModuleContext) -> None:
        parameters: dict = dict(ctx.config['path_tracking_parameters'])
        local: dict = dict(ctx.config['local_navigation_parameters'])
        self.path_xy: NDArray[np.float64] = readonly_path(parameters['reference']['points_m'])
        self.limits: dict = dict(parameters['control_limits'])
        self.max_age_ticks: int = local['input_max_age_ticks']
        self.tick_duration_s: float = local['tick_duration_s']
        self.follower: PathFollower = PathFollower(parameters['reference_speed_mps'], self.limits['max_vx_mps'],
                                                   self.limits['max_wz_radps'], parameters['position_tolerance_m'])
        self.controller: LocalController = LocalController(
            DifferentialDriveParameters(**ctx.config['drive_parameters']), local['robot_radius_m'],
            local['safety_margin_m'], self.limits['max_vx_mps'], self.limits['max_wz_radps'], local['command_delay_s'])

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.setup(ctx)

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        samples: dict = {name: inputs.latest(name) for name in ('pose','scan','wheels')}
        ages: dict = {name: None if sample is None else (ctx.simulation_tick-sample.simulation_tick)*self.tick_duration_s
                      for name,sample in samples.items()}
        invalid: list[str] = []
        for name,sample in samples.items():
            expected_frame: str = 'map' if name == 'pose' else 'base_link'
            if sample is None:
                invalid.append(name+'_missing')
            elif sample.frame_id != expected_frame:
                invalid.append(name+'_frame')
            elif not 0 <= ctx.simulation_tick-sample.simulation_tick <= self.max_age_ticks:
                invalid.append(name+'_stale')
        pose, scan, wheels = (samples[name] for name in ('pose','scan','wheels'))
        if scan is not None and (not isinstance(scan.data, Scan2D) or scan.data.sample_tick != scan.simulation_tick):
            invalid.append('scan_unavailable')
        if pose is not None and (not isinstance(pose.data, Pose2D) or pose.data.child_frame_id != 'base_link'):
            invalid.append('pose_unavailable')
        if wheels is not None and (any(name not in wheels.data.name for name in ('left','right')) or len(wheels.data.velocity) != len(wheels.data.name)):
            invalid.append('wheels_unavailable')
        nominal: Twist = Twist()
        final: Twist = Twist()
        if not invalid:
            estimated: NDArray[np.float64] = np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad], dtype=np.float64)
            rates: NDArray[np.float64] = np.array([wheels.data.velocity[wheels.data.name.index(name)] for name in ('left','right')], dtype=np.float64)
            if not np.isfinite(estimated).all() or not np.isfinite(rates).all():
                invalid.append('nonfinite_input')
            else:
                nominal = checked_command(self.follower.update(estimated, self.path_xy, ctx.dt_seconds), self.limits)
                observation: LocalControlInput = LocalControlInput(estimated, self.path_xy, scan.data, nominal,
                    ages['pose'], ages['scan'], rates, ages['wheels'])
                final = checked_command(self.controller.update(observation, ctx.dt_seconds), self.limits)
        ctx.publish('command', final, frame_id='base_link')
        ctx.publish('feedback', LocalControlFeedback(nominal.linear.x, nominal.angular.z, final.linear.x, final.angular.z,
                    ages['pose'], ages['scan'], ages['wheels'], ','.join(invalid) if invalid else 'ok'), frame_id='base_link')
