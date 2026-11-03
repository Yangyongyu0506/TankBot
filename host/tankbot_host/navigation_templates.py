"""Reusable wheel-controller scaffolding; no executable code is read from level YAML."""

CONTROLLER = '''"""双轮差速控制算法；此文件全部保留，可增加辅助函数。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters, Twist


class WheelController:
    def __init__(self, model: DifferentialDriveParameters) -> None:
        self.model: DifferentialDriveParameters = model
        self.integral_error: NDArray[np.float64] = np.zeros(2, dtype=np.float64)

    def control(
        self,
        target: Twist,
        wheel_rates_radps: NDArray[np.float64],
        dt: float,
    ) -> NDArray[np.float64]:
        """输入目标 Twist、当前左右轮角速度和仿真 dt；返回 [左电压,右电压]。

        target.linear.x: m/s；target.angular.z: rad/s，逆时针为正。
        wheel_rates_radps: 只读 float64 数组，shape=(2,)，顺序 [left,right]。
        dt: 本次与上次调用间的仿真秒，不是墙上时钟。
        返回有限 float64 NumPy 数组，shape=(2,)，单位 V；框架执行电压限幅。
        self.model 提供轮径、轮距、车体和电机参数，均来自 YAML。
        self.integral_error 可保存两轮积分状态；每次部署/重试重新初始化。

        TODO：实现 FK/IK，将车体目标转换为轮速目标，再结合电机状态方程
        和轮速反馈计算电压。零电压会电气制动，不是保持当前位置。
        """
        voltage_v: NDArray[np.float64] = np.zeros(2, dtype=np.float64)
        return voltage_v
'''

ADAPTER = '''"""系统管理的双轮控制适配器；算法保存在 control/wheel_controller.py。"""
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
'''
