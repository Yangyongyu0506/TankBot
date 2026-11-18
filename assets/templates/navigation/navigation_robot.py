"""系统管理的双轮控制适配器；算法保存在 control/wheel_controller.py。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import (
    DifferentialDriveParameters, Inputs, JointState, Module, ModuleContext,
    Sample, Twist, WheelVoltage,
)
from control.wheel_controller import WheelController


class WheelControlModule(Module):
    scaffold_api: str = "wheel_voltage@1"

    def setup(self, ctx: ModuleContext) -> None:
        self.controller: WheelController = WheelController(
            DifferentialDriveParameters(**dict(ctx.config["drive_parameters"]))
        )

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.setup(ctx)

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        command: Sample[Twist] | None = inputs.latest("command")
        wheels: Sample[JointState] | None = inputs.latest("wheels")
        if command is None or wheels is None:
            return
        state: JointState = wheels.data
        rates: NDArray[np.float64] = np.array(
            [state.velocity[state.name.index("left")], state.velocity[state.name.index("right")]],
            dtype=np.float64,
        )
        rates = np.frombuffer(rates.tobytes(), dtype=np.float64)
        voltage: NDArray[np.float64] = self.controller.control(command.data, rates, ctx.dt_seconds)
        if not isinstance(voltage, np.ndarray) or voltage.shape != (2,) or voltage.dtype != np.float64:
            raise TypeError("control 必须返回 shape=(2,) 的 float64 NumPy 数组，顺序为 [left_voltage_v,right_voltage_v]")
        if not np.isfinite(voltage).all():
            raise ValueError("control 返回的两轮电压必须有限，不能是 NaN/Inf")
        ctx.publish("voltage", WheelVoltage(float(voltage[0]), float(voltage[1])), frame_id="base_link")
