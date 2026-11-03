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

ODOMETRY = '''"""差速轮式里程计；此文件全部保留，只使用轮速与公开初始位姿。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters


class Odometry:
    def __init__(
        self,
        model: DifferentialDriveParameters,
        initial_pose: NDArray[np.float64],
    ) -> None:
        self.model: DifferentialDriveParameters = model
        self.pose: NDArray[np.float64] = initial_pose.copy()

    def update(
        self,
        wheel_rates_radps: NDArray[np.float64],
        dt: float,
    ) -> NDArray[np.float64]:
        """根据实际轮速积分地图系位姿，返回 [x_m,y_m,yaw_rad]。

        wheel_rates_radps: 只读 float64 (2,)，顺序 [left,right]，单位 rad/s。
        dt: 本次与上次已处理编码器采样之间的仿真秒。
        初始位姿仅在构造时提供一次，self.pose 保存你自己的当前估计。
        轮半径 r 与轮距 B 来自 self.model；不要使用目标 Twist 代替实测轮速。
        返回有限 float64 (3,) NumPy 数组；yaw 的发布归一化由框架处理。

        TODO：先从左右轮速计算车体 v/w，再将车体系速度转到地图系并积分。
        你可以选择 Euler、中点或其他积分方法，不需要维护无界历史。
        """
        return self.pose.copy()
'''

ODOMETRY_ADAPTER = '''"""系统管理的里程计适配器；只发布估计，不影响真实车体。"""
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
'''
