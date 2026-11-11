"""玩家维护：利用车体系扫描避障；框架不提供隐藏避障器。"""
from tankbot import DifferentialDriveParameters, LocalControlInput, Twist


class LocalController:
    def __init__(self, model: DifferentialDriveParameters, robot_radius_m: float,
                 safety_margin_m: float, max_vx_mps: float, max_wz_radps: float,
                 command_delay_s: float) -> None:
        """公开模型、圆形安全半径与两级固定提交延迟；不包含真实状态。"""
        self.model: DifferentialDriveParameters = model
        self.robot_radius_m: float = robot_radius_m
        self.safety_margin_m: float = safety_margin_m
        self.max_vx_mps: float = max_vx_mps
        self.max_wz_radps: float = max_wz_radps
        self.command_delay_s: float = command_delay_s

    def update(self, observation: LocalControlInput, dt: float) -> Twist:
        """返回最终车体系Twist；自主减速、绕行及接回路线，不直接驱动物理。

        scan.ranges_m / hit_mask 为不可变当前整帧；angles_rad 正向逆时针。
        estimated_pose 与 reference_path 位于map；扫描属于其原sample tick的base_link。
        轮速是与EKF相同的带噪观测，名义Twist不是实测速度。
        command_delay_s 还需加 scan_age_s；考虑制动、车体半径与安全余量。
        """
        raise NotImplementedError("请实现局部避障，不要把名义指令当作实测速度")
