"""系统管理的连续追踪适配器；只读取静态公开路径和玩家EKF。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import Inputs, Module, ModuleContext, Pose2D, Sample, Twist, Vector3, readonly_path
from navigation.path_follower import PathFollower


class PathTrackingModule(Module):
    scaffold_api: str = "path_tracking@1"

    def setup(self, ctx: ModuleContext) -> None:
        parameters: dict = dict(ctx.config["path_tracking_parameters"])
        self.path_xy: NDArray[np.float64] = readonly_path(parameters["reference"]["points_m"])
        self.path_id: str = parameters["reference"]["path_id"]
        self.limits: dict = dict(parameters["control_limits"])
        self.pose_max_age_ticks: int = parameters["pose_max_age_ticks"]
        self.controller: PathFollower = PathFollower(
            reference_speed_mps=parameters["reference_speed_mps"],
            max_vx_mps=self.limits["max_vx_mps"], max_wz_radps=self.limits["max_wz_radps"],
            position_tolerance_m=parameters["position_tolerance_m"],
        )

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.setup(ctx)

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = inputs.latest("pose")
        command: Twist = Twist()
        if (pose is not None and pose.frame_id == "map"
                and 0 <= ctx.simulation_tick-pose.simulation_tick <= self.pose_max_age_ticks):
            estimated_pose: NDArray[np.float64] = np.frombuffer(np.array(
                [pose.data.x_m, pose.data.y_m, pose.data.yaw_rad], dtype=np.float64
            ).tobytes(), dtype=np.float64)
            command = self.controller.update(estimated_pose, self.path_xy, ctx.dt_seconds)
        if not isinstance(command, Twist) or not isinstance(command.linear, Vector3) or not isinstance(command.angular, Vector3):
            raise TypeError("PathFollower.update 必须返回Twist，linear/angular须为Vector3")
        values: list[float] = [command.linear.x, command.linear.y, command.linear.z,
                              command.angular.x, command.angular.y, command.angular.z]
        if any(isinstance(value, bool) or not isinstance(value, (int,float,np.integer,np.floating)) for value in values):
            raise TypeError("Twist各分量必须为实数，不能是字符串或布尔值")
        if not np.isfinite(values).all():
            raise ValueError("PathFollower.update 返回的Twist不能含NaN/Inf")
        if any(values[index] != 0 for index in (1,2,3,4)):
            raise ValueError("差速Twist仅允许linear.x/angular.z；其他分量须为0")
        if command.linear.x < self.limits["min_vx_mps"]:
            raise ValueError("本关禁止主动倒车：linear.x必须非负，允许零速度及原地转向")
        bounded: Twist = Twist(
            linear=Vector3(x=float(min(command.linear.x,self.limits["max_vx_mps"]))),
            angular=Vector3(z=float(np.clip(command.angular.z,-self.limits["max_wz_radps"],self.limits["max_wz_radps"]))),
        )
        ctx.publish("command", bounded, frame_id="base_link")
