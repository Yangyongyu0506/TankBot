"""连续路径追踪算法；本文件完整保留，可增加辅助函数和跨帧状态。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import Twist, Vector3


class PathFollower:
    def __init__(self, reference_speed_mps: float, max_vx_mps: float,
                 max_wz_radps: float, position_tolerance_m: float) -> None:
        self.reference_speed_mps: float = reference_speed_mps
        self.max_vx_mps: float = max_vx_mps
        self.max_wz_radps: float = max_wz_radps
        self.position_tolerance_m: float = position_tolerance_m

    def update(self, estimated_pose: NDArray[np.float64],
               path_xy: NDArray[np.float64], dt: float) -> Twist:
        """根据自己的EKF和完整公开路径计算车体系Twist参考。

        estimated_pose: 只读float64 (3,)，map系[x_m,y_m,yaw_rad]，来自你的EKF。
        path_xy: 只读float64 (N,2)，map系米制坐标；path_xy[i]是第i行[x,y]。
          path_xy[0]为起点，path_xy[-1]为终点，按起终点方向排列，无连续重复点。
          最终折线弧长间隔0.10m，末段可短于0.10m；完整路径只在准备阶段生成。
        dt: 本追踪器执行间隔，单位仿真秒，不是渲染间隔或GPS周期。
        返回: tankbot.Twist(linear=Vector3(x=v), angular=Vector3(z=w))。
          v单位m/s，范围[0,max_vx_mps]；w单位rad/s，范围±max_wz_radps。
          vy及非平面分量为0。允许减速/原地转向，禁止负v，不设最低速度。

        连续追踪不是逐点停车：可计算最近线段、累计弧长和前视点，再求角误差。
        用atan2(sin(error),cos(error))处理角度环绕；弯道及终点附近应主动减速。
        全路径为参考而非传感器，位置仍可能有EKF误差。框架处理部署/Topic/轮电压。
        TODO: 自行选择连续追踪控制律，考虑固定提交延迟，抵达末点后制动停稳。
        """
        return Twist()
