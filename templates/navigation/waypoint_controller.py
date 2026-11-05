"""位置闭环算法；此文件全部保留，可增加辅助函数和跨帧状态。"""
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
