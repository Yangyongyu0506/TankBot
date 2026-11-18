"""系统管理的位置控制适配器；只读取玩家EKF和公开目标。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import Inputs, Module, ModuleContext, Pose2D, Sample, Twist, Vector3, WaypointGoal
from navigation.waypoint_controller import WaypointController


class WaypointNavigationModule(Module):
    scaffold_api: str = "waypoint_control@1"

    def setup(self, ctx: ModuleContext) -> None:
        parameters: dict = dict(ctx.config["navigation_parameters"])
        self.limits: dict = dict(parameters["control_limits"])
        self.pose_max_age_ticks: int = parameters["pose_max_age_ticks"]
        self.controller: WaypointController = WaypointController(
            position_tolerance_m=parameters["position_tolerance_m"],
            max_vx_mps=self.limits["max_vx_mps"],
            max_wz_radps=self.limits["max_wz_radps"],
        )

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.setup(ctx)

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = inputs.latest("pose")
        goal: Sample[WaypointGoal] | None = inputs.latest("goal")
        command: Twist = Twist()
        if (pose is not None and goal is not None and pose.frame_id == "map" and goal.frame_id == "map"
                and 0 <= ctx.simulation_tick-pose.simulation_tick <= self.pose_max_age_ticks):
            estimate: NDArray[np.float64] = np.frombuffer(np.array(
                [pose.data.x_m, pose.data.y_m, pose.data.yaw_rad], dtype=np.float64
            ).tobytes(), dtype=np.float64)
            command = self.controller.update(estimate, goal.data.position_m, ctx.dt_seconds)
        if not isinstance(command, Twist) or not isinstance(command.linear, Vector3) or not isinstance(command.angular, Vector3):
            raise TypeError("WaypointController.update 必须返回 Twist，linear/angular 必须为 Vector3")
        values: list[float] = [command.linear.x, command.linear.y, command.linear.z,
                               command.angular.x, command.angular.y, command.angular.z]
        if any(isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)) for value in values):
            raise TypeError("Twist 各分量必须是实数，不能是字符串或布尔值")
        if not np.isfinite(values).all():
            raise ValueError("WaypointController.update 返回的 Twist 不能包含 NaN/Inf")
        if any(values[index] != 0 for index in (1, 2, 3, 4)):
            raise ValueError("差速底盘 Twist 仅允许 linear.x / angular.z；vy及其他分量必须为0")
        bounded: Twist = Twist(
            linear=Vector3(x=float(np.clip(command.linear.x, -self.limits["max_vx_mps"], self.limits["max_vx_mps"]))),
            angular=Vector3(z=float(np.clip(command.angular.z, -self.limits["max_wz_radps"], self.limits["max_wz_radps"]))),
        )
        ctx.publish("command", bounded, frame_id="base_link")
