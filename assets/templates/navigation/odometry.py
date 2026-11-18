"""差速轮式里程计；此文件全部保留，只使用轮速与公开初始位姿。"""
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
