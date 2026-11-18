"""系统管理的 EKF 采样、GPS 去重和发布；算法位于 localization/ekf.py。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import (
    DifferentialDriveParameters, Inputs, JointState, Module, ModuleContext,
    Pose2D, PositionFix2D, Sample,
)
from localization.ekf import EkfLocalization


def readonly_array(value: object) -> NDArray[np.float64]:
    array: NDArray[np.float64] = np.array(value, dtype=np.float64)
    return np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)


class EkfLocalizationModule(Module):
    scaffold_api: str = "wheel_gps_ekf@1"

    def setup(self, ctx: ModuleContext) -> None:
        parameters: dict = dict(ctx.config["localization_parameters"])
        self.filter: EkfLocalization = EkfLocalization(
            DifferentialDriveParameters(**dict(ctx.config["drive_parameters"])),
            readonly_array(ctx.config["initial_pose"]),
            readonly_array(ctx.config["module"]["initial_covariance"]),
            readonly_array(parameters["wheel_rate_covariance"]),
            readonly_array(parameters["gain_error_bounds"]),
        )
        self.last_sample_tick: int = ctx.simulation_tick
        self.last_gps_tick: int = ctx.simulation_tick

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.setup(ctx)

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        wheels: Sample[JointState] | None = inputs.latest("wheels")
        gps: Sample[PositionFix2D] | None = inputs.latest("gps")
        if wheels is None or wheels.simulation_tick <= self.last_sample_tick:
            return
        state: JointState = wheels.data
        rates: NDArray[np.float64] = readonly_array([
            state.velocity[state.name.index("left")], state.velocity[state.name.index("right")]
        ])
        dt: float = (wheels.simulation_tick-self.last_sample_tick)*ctx.config["lesson"]["tick_duration_s"]
        result: object = self.filter.predict(rates, dt)
        if result is not None:
            raise TypeError("EkfLocalization.predict 应更新 self.state/self.covariance 并返回 None")
        if gps is not None and gps.simulation_tick > self.last_gps_tick:
            self.last_gps_tick = gps.simulation_tick
            if gps.simulation_tick == wheels.simulation_tick:
                result = self.filter.correct(gps.data.position_m, gps.data.covariance)
                if result is not None:
                    raise TypeError("EkfLocalization.correct 应更新 self.state/self.covariance 并返回 None")
            else:
                print("跳过未对齐的 GPS：GPS tick=", gps.simulation_tick,
                      "，当前编码器 tick=", wheels.simulation_tick)
        estimate: NDArray[np.float64] = self.filter.state
        covariance: NDArray[np.float64] = self.filter.covariance
        for name, array, shape in (("state", estimate, (3,)), ("covariance", covariance, (3, 3))):
            if not isinstance(array, np.ndarray) or array.dtype != np.float64 or array.shape != shape:
                raise TypeError("EkfLocalization."+name+" 必须是 float64 NumPy 数组，shape="+str(shape))
            if not np.isfinite(array).all():
                raise ValueError("EkfLocalization."+name+" 不能包含 NaN/Inf")
        self.last_sample_tick = wheels.simulation_tick
        ctx.publish("pose", Pose2D(float(estimate[0]), float(estimate[1]),
                    float((estimate[2]+np.pi)%(2*np.pi)-np.pi), covariance=covariance),
                    frame_id="map", simulation_tick=wheels.simulation_tick)
