"""系统管理的里程计适配器；只发布估计，不影响真实车体。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters, Inputs, JointState, Module, ModuleContext, Pose2D, Sample
from localization.odometry import Odometry


class WheelOdometryModule(Module):
    scaffold_api: str = "wheel_odometry@1"

    def setup(self, ctx: ModuleContext) -> None:
        initial_pose: NDArray[np.float64] = np.frombuffer(
            np.array(ctx.config["initial_pose"], dtype=np.float64).tobytes(), dtype=np.float64
        )
        self.odometry: Odometry = Odometry(
            DifferentialDriveParameters(**dict(ctx.config["drive_parameters"])), initial_pose
        )
        self.last_sample_tick: int = ctx.simulation_tick

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.setup(ctx)

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        wheels: Sample[JointState] | None = inputs.latest("wheels")
        if wheels is None or wheels.simulation_tick <= self.last_sample_tick:
            return
        state: JointState = wheels.data
        rates: NDArray[np.float64] = np.frombuffer(np.array(
            [state.velocity[state.name.index("left")], state.velocity[state.name.index("right")]],
            dtype=np.float64,
        ).tobytes(), dtype=np.float64)
        dt: float = (wheels.simulation_tick-self.last_sample_tick)*ctx.config["lesson"]["tick_duration_s"]
        estimate: NDArray[np.float64] = self.odometry.update(rates, dt)
        if not isinstance(estimate, np.ndarray) or estimate.shape != (3,) or estimate.dtype != np.float64:
            raise TypeError("Odometry.update 必须返回 shape=(3,) 的 float64 NumPy 数组：[x_m,y_m,yaw_rad]")
        if not np.isfinite(estimate).all():
            raise ValueError("里程计输出必须有限，不能是 NaN/Inf")
        self.last_sample_tick = wheels.simulation_tick
        ctx.publish("pose", Pose2D(float(estimate[0]), float(estimate[1]),
                    float((estimate[2]+np.pi)%(2*np.pi)-np.pi)),
                    frame_id="map", simulation_tick=wheels.simulation_tick)
