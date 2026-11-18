"""轮速与 GPS 融合定位；此文件全部保留，可增加辅助函数。"""
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
