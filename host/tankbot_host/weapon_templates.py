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
        """Algorithm input/output contract; see level guidance."""
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
        """Algorithm input/output contract; see level guidance."""
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
        """Algorithm input/output contract; see level guidance."""
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
