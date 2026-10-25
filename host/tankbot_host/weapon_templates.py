"""Weapons chapter scaffolds: numerical algorithms stay in player-owned files."""

AUTO_AIM = '''import numpy as np
from numpy.typing import NDArray
from tankbot import AimInput, AimOutput


class AutoAim:
    def __init__(self, projectile_speed_mps: float, max_acceleration_radps2: float) -> None:
        self.projectile_speed_mps: float = projectile_speed_mps
        self.max_acceleration_radps2: float = max_acceleration_radps2
        self.previous_target: NDArray[np.float64] | None = None

    def update(self, observation: AimInput, dt: float) -> AimOutput:
        """输入仅含本关授权数据，不需要自己处理 Topic 或 JSON。

        observation.target_xy: None 或 shape=(2,) 的地图目标估计 [x,y]，单位 m。
        observation.target_age_s: 在本批控制提交时，该目标估计已过去的仿真秒。
        observation.own_pose: shape=(3,) 的系统自身位姿 [x,y,yaw]，单位 m、rad。
        observation.turret_angle_rad: 炮台相对车体的累计角，rad（允许连续旋转）。
        observation.turret_rate_radps: 相对角速度，rad/s。
        observation.weapon_ready: 本机武器当前是否已冷却完成。
        dt: 本模块两次实际调用间的仿真秒；与传感器采样间隔并非同一概念。
        返回 AimOutput(acceleration_radps2=相对角加速度, fire=是否请求单发)。

        先用目标与自身位置计算期望朝向；角误差用 atan2(sin(e),cos(e))。
        只能输出角加速度，不可直接设角度/角速度；考虑角速度反馈与制动。
        可以用跨调用的 NumPy 状态估计目标速度，补偿观测延迟和飞行时间。
        没有目标时不要盲射。框架负责冷却检查、幂等请求与控制权限。
        """
        # TODO: 实现转向、制动、运动预测与开火条件。零输出可以先部署观察。
        return AimOutput(acceleration_radps2=0.0, fire=False)
'''

POSE_TRACKER = '''import numpy as np
from numpy.typing import NDArray
from tankbot import TargetPoseEstimate


class PoseTracker:
    def __init__(self) -> None:
        self.estimate: TargetPoseEstimate | None = None
        self.previous_position: NDArray[np.float64] | None = None

    def update(self, measurements: NDArray[np.float64], dt: float) -> TargetPoseEstimate | None:
        """measurements 是本帧敌车底盘中心的地图测量，shape=(N,2)，N 为 0 或 1。
        列为 x/y，单位 m；空数组 shape=(0,2)，不是历史轨迹。
        dt 为距上次调用的仿真秒。返回敌车中心 x/y、车头 yaw 的估计；None 表示尚无估计。
        TargetPoseEstimate(x_m: float, y_m: float, yaw_rad: float, covariance=None)。
        yaw 是 map +x 起逆时针弧度，归一化到 [-pi,pi)；协方差可空或 (3,3) NumPy 矩阵。
        敌车本关仅向车头前进、可原地转向，不倒车；运动时可由平滑轨迹估计航向。
        仅凭中心位置不能唯一知道原地转向时的 yaw；应预测/保持并表达不确定性。
        保留带上限的历史或固定维数的 NumPy 状态，不要无限追加。
        """
        # TODO: 复用 C2 的位置估计思路，同时估计敌车航向。
        return self.estimate
'''

ARMOR_AIM = '''import numpy as np
from numpy.typing import NDArray
from tankbot import AimInput, AimOutput
from weapons.auto_aim import AutoAim


class ArmorAim:
    def __init__(self, projectile_speed_mps: float, max_acceleration_radps2: float,
                 armor_mounts: NDArray[np.float64]) -> None:
        self.controller: AutoAim = AutoAim(projectile_speed_mps, max_acceleration_radps2)
        # 每行是 [安装 x, 安装 y, 向外法线 yaw]，参考系为敌车底盘。
        self.armor_mounts: NDArray[np.float64] = armor_mounts

    def update(self, observation: AimInput, dt: float) -> AimOutput:
        """输入与 C3 一致，但 target_xy 是敌车底盘中心，target_yaw_rad 是玩家估计的敌车朝向。
        雷达始终观测底盘中心，不会给真实 yaw 或装甲坐标。
        armor_mounts: shape=(4,3)，安装偏移单位 m、法线角单位 rad。
        公开差速模型：车体系 vy=0，只前进，可原地转向；具体巡逻路径不是传感器数据。
        将装甲安装偏移用估计 yaw 旋转后加上中心位置，得到地图瞄准点。
        可复用 C1 的矩阵方法、C3 AutoAim 的控制逻辑，并考虑敌车未来姿态。
        没有可靠 yaw 时可保持/预测或暂不射击。输出仍只能是角加速度和单发意图。
        """
        # TODO: 选择可击中的装甲并计算瞄准点，然后复用/扩展 C3 控制器。
        return AimOutput(acceleration_radps2=0.0, fire=False)
'''

MODULES = '''# TankBot Weapons module adapters. Algorithms live in perception/ and weapons/.
from __future__ import annotations
from typing import cast
import numpy as np
from numpy.typing import NDArray
from tankbot import (Module, ModuleContext, Inputs, Sample, Pose2D, RadarData, RadarDetection, JointState,
                     WeaponState, TargetEstimate, TargetPoseEstimate, TargetPoints,
                     TurretAcceleration, AimInput, AimOutput)
from tankbot.transforms import radar_point, validate_se3


class CoordinatesModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        self.last_tick: int | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None", inputs.latest("self_pose"))
        radar: Sample[RadarData] | None = cast("Sample[RadarData] | None", inputs.latest("radar"))
        if pose is None or radar is None or radar.simulation_tick == self.last_tick:
            return
        self.last_tick = radar.simulation_tick
        from perception.transforms import radar_to_map
        transform: NDArray[np.float64] = validate_se3(radar_to_map(pose.data), tolerance=ctx.config["lesson"]["transform_tolerance"])
        points: NDArray[np.float64] = np.empty((len(radar.data.detections), 2), dtype=np.float64)
        index: int
        detection: RadarDetection
        for index, detection in enumerate(radar.data.detections):
            points[index] = (transform @ radar_point(detection))[:2]
        ctx.publish("points", TargetPoints(points), frame_id="map", simulation_tick=radar.simulation_tick)


class TrackingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from perception.tracker import Tracker
        self.tracker: Tracker = Tracker()
        self.last_tick: int | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        points: Sample[TargetPoints] | None = cast("Sample[TargetPoints] | None", inputs.latest("points"))
        if points is None or points.simulation_tick == self.last_tick:
            return
        self.last_tick = points.simulation_tick
        measurements: tuple[TargetEstimate, ...] = tuple(TargetEstimate(float(row[0]),float(row[1])) for row in points.data.positions_m)
        estimate: TargetEstimate | None = self.tracker.update(measurements,ctx.dt_seconds)
        if estimate is not None:
            ctx.publish("target",estimate,frame_id="map",simulation_tick=points.simulation_tick)


class PoseTrackingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from perception.pose_tracker import PoseTracker
        self.tracker: PoseTracker = PoseTracker()
        self.last_tick: int | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        points: Sample[TargetPoints] | None = cast("Sample[TargetPoints] | None", inputs.latest("points"))
        if points is None or points.simulation_tick == self.last_tick:
            return
        self.last_tick = points.simulation_tick
        estimate: TargetPoseEstimate | None = self.tracker.update(points.data.positions_m,ctx.dt_seconds)
        if estimate is not None:
            ctx.publish("target",estimate,frame_id="map",simulation_tick=points.simulation_tick)


class AimingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from weapons.auto_aim import AutoAim
        from weapons.armor_aim import ArmorAim
        self.armor_mode: bool = bool(ctx.config["actuators"]["armor_mounts"])
        self.controller: AutoAim | ArmorAim = (ArmorAim(ctx.config["actuators"]["projectile_speed_mps"],ctx.config["actuators"]["max_acceleration_radps2"],np.array(ctx.config["actuators"]["armor_mounts"],dtype=np.float64))
            if self.armor_mode else AutoAim(ctx.config["actuators"]["projectile_speed_mps"],ctx.config["actuators"]["max_acceleration_radps2"]))

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None", inputs.latest("self_pose"))
        turret: Sample[JointState] | None = cast("Sample[JointState] | None", inputs.latest("turret"))
        weapon: Sample[WeaponState] | None = cast("Sample[WeaponState] | None", inputs.latest("weapon"))
        target: Sample[TargetEstimate | TargetPoseEstimate] | None = cast("Sample[TargetEstimate | TargetPoseEstimate] | None", inputs.latest("target"))
        if pose is None or turret is None or weapon is None:
            return
        observation: AimInput = AimInput(
            target_xy=np.array([target.data.x_m,target.data.y_m],dtype=np.float64) if target is not None else None,
            target_age_s=(ctx.output_commit_tick-target.simulation_tick)*ctx.config["lesson"]["tick_duration_s"] if target is not None else 0.0,
            own_pose=np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64),
            turret_angle_rad=turret.data.position[0],turret_rate_radps=turret.data.velocity[0],weapon_ready=weapon.data.ready,
            target_yaw_rad=target.data.yaw_rad if target is not None and isinstance(target.data,TargetPoseEstimate) else None)
        result: AimOutput = self.controller.update(observation,ctx.dt_seconds)
        if not isinstance(result,AimOutput) or not isinstance(result.fire,(bool,np.bool_)):
            raise TypeError("自瞄算法必须返回 AimOutput(acceleration_radps2: float, fire: bool)")
        ctx.publish("acceleration",TurretAcceleration(result.acceleration_radps2),frame_id="base_link")
        if result.fire and weapon.data.ready:
            ctx.fire("fire")
'''

TEST = '''import unittest
import numpy as np
from tankbot import AimInput, AimOutput
from weapons.auto_aim import AutoAim


class AutoAimContractTest(unittest.TestCase):
    def test_no_target_output_contract(self) -> None:
        controller: AutoAim = AutoAim(projectile_speed_mps=1.0,max_acceleration_radps2=1.0)
        observation: AimInput = AimInput(None,0.0,np.zeros(3,dtype=np.float64),0.0,0.0,True)
        result: AimOutput = controller.update(observation,dt=1.0)
        self.assertIsInstance(result,AimOutput)
        self.assertIsInstance(result.fire,bool)
        self.assertTrue(np.isfinite(result.acceleration_radps2))
'''


def sources(level):
    from .campaign_templates import TRANSFORMS, TRACKER, COORDINATE_TEST
    result = {"robot_modules/__init__.py":"","robot_modules/weapons.py":MODULES,
              "perception/__init__.py":"","perception/transforms.py":TRANSFORMS,"perception/tracker.py":TRACKER,
              "weapons/__init__.py":"","weapons/auto_aim.py":AUTO_AIM,"weapons/armor_aim.py":ARMOR_AIM,
              "tests/test_coordinates.py":COORDINATE_TEST,"tests/test_auto_aim.py":TEST}
    if level.get("armor_mode"):
        result["perception/pose_tracker.py"] = POSE_TRACKER
    return result
