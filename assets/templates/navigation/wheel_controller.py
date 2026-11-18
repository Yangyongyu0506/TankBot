"""双轮差速控制算法；此文件全部保留，可增加辅助函数。"""
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
