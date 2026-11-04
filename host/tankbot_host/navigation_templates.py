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

EKF = '''"""轮速与 GPS 融合定位；此文件全部保留，可增加辅助函数。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import DifferentialDriveParameters


class EkfLocalization:
    def __init__(
        self,
        model: DifferentialDriveParameters,
        initial_pose: NDArray[np.float64],
        initial_covariance: NDArray[np.float64],
        wheel_rate_covariance: NDArray[np.float64],
        gain_error_bounds: NDArray[np.float64],
    ) -> None:
        self.model: DifferentialDriveParameters = model
        self.state: NDArray[np.float64] = initial_pose.copy()
        self.covariance: NDArray[np.float64] = initial_covariance.copy()
        self.wheel_rate_covariance: NDArray[np.float64] = wheel_rate_covariance
        self.gain_error_bounds: NDArray[np.float64] = gain_error_bounds

    def predict(self, wheel_rates_radps: NDArray[np.float64], dt: float) -> None:
        """用带噪左右轮速预测状态及协方差；修改 self.state/self.covariance。

        wheel_rates_radps: 只读 float64 (2,)，[left,right]，rad/s。
        dt: 两次已处理编码器采样的仿真时间差，s。
        self.state: 可写 float64 (3,)，地图系 [x_m,y_m,yaw_rad]。
        self.covariance: 可写 float64 (3,3)，顺序 [x,y,yaw]，对称半正定。
        返回 None。不要返回 Pose2D，不需要维护历史或访问真实位置。
        模型与噪声先验均由框架提供；F2 指南列出 f/F/G/Q 的含义。

        TODO：非线性运动预测 state=f(state,wheels,dt)，再传播协方差。
        """
        pass

    def correct(
        self,
        position_m: NDArray[np.float64],
        measurement_covariance: NDArray[np.float64],
    ) -> None:
        """使用一条新 GPS 测量校正 self.state 和 self.covariance，返回 None。

        position_m: 只读 float64 (2,)，map 系 [x_m,y_m]，不是 Ground Truth。
        measurement_covariance: 只读 float64 (2,2)，单位 m²。
        框架已去重并对齐到本次预测时刻；同一 GPS 不会重复调用。
        GPS 不测 yaw，但状态之间的协方差可使位置观测间接校正 yaw。

        TODO：计算 innovation/S/K，校正状态，保持协方差对称半正定。
        """
        pass
'''

EKF_ADAPTER = '''"""系统管理的 EKF 采样、GPS 去重和发布；算法位于 localization/ekf.py。"""
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
'''

WAYPOINT_CONTROLLER = '''"""位置闭环算法；此文件全部保留，可增加辅助函数和跨帧状态。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import Twist, Vector3


class WaypointController:
    def __init__(
        self,
        position_tolerance_m: float,
        max_vx_mps: float,
        max_wz_radps: float,
    ) -> None:
        self.position_tolerance_m: float = position_tolerance_m
        self.max_vx_mps: float = max_vx_mps
        self.max_wz_radps: float = max_wz_radps

    def update(
        self,
        estimated_pose: NDArray[np.float64],
        target_xy: NDArray[np.float64],
        dt: float,
    ) -> Twist:
        """从自己的定位估计与当前目标计算车体系速度参考。

        estimated_pose: 只读float64 (3,)，map系 [x_m,y_m,yaw_rad]；来自你的EKF。
        target_xy: 只读float64 (2,)，map系当前航点 [x_m,y_m]；不是位置观测。
        dt: 本位置控制器两次执行之间的仿真秒，不是GPS间隔或渲染帧时间。
        返回tankbot.Twist：linear.x为车体前进速度m/s，angular.z为逆时针rad/s。
        linear.y及其他二维模型未使用分量必须为0。框架限幅，再交给轮电压控制器。
        可以用Twist(linear=Vector3(x=v), angular=Vector3(z=w))构造输出。

        公开容差与速度上限来自YAML。构造/reset由框架处理，航点切换无需你管理。
        TODO：计算目标距离与最短弧航向误差，形成反馈并在接近目标时减速停稳。
        可自行选择控制律，不要按仿真时间硬编码直行/转向。
        """
        return Twist()
'''

WAYPOINT_ADAPTER = '''"""系统管理的位置控制适配器；只读取玩家EKF和公开目标。"""
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
'''
