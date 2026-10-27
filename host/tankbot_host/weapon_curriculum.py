"""Reusable raw-observation and prediction scaffolds. No executable level plugins."""

ARMOR_TRACKER = '''import numpy as np
from numpy.typing import NDArray
from tankbot import TargetPoseEstimate


class ArmorTracker:
    def __init__(self, armor_mounts: NDArray[np.float64],
                 measurement_covariance: NDArray[np.float64]) -> None:
        self.armor_mounts: NDArray[np.float64] = armor_mounts
        self.measurement_covariance: NDArray[np.float64] = measurement_covariance
        self.estimate: TargetPoseEstimate | None = None

    def update(self, measurements_rt: NDArray[np.float64], own_pose: NDArray[np.float64],
               dt: float) -> TargetPoseEstimate | None:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 匿名装甲关联与状态估计；yaw 只需描述模 90 度的等价朝向。
        return self.estimate
'''

ARMOR_ADAPTER = '''# TankBot armor observation adapter; estimation is player-owned.
from typing import cast
import numpy as np
from numpy.typing import NDArray
from tankbot import Module, ModuleContext, Inputs, Sample, Pose2D, ArmorDetections, TargetPoseEstimate


class ArmorTrackingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from perception.armor_tracker import ArmorTracker
        calibration: dict = dict(ctx.config["observations"])
        self.tracker: ArmorTracker = ArmorTracker(np.array(calibration["armor_mounts"],dtype=np.float64),np.array(calibration["armor_covariance"],dtype=np.float64))
        self.last_tick: int | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None",inputs.latest("self_pose"))
        armor: Sample[ArmorDetections] | None = cast("Sample[ArmorDetections] | None",inputs.latest("armor"))
        if pose is None or armor is None or pose.simulation_tick!=armor.simulation_tick or armor.simulation_tick==self.last_tick:
            return
        dt: float = (armor.simulation_tick-self.last_tick)*ctx.config["lesson"]["tick_duration_s"] if self.last_tick is not None else ctx.dt_seconds
        self.last_tick = armor.simulation_tick
        own: NDArray[np.float64] = np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64)
        estimate: TargetPoseEstimate | None = self.tracker.update(armor.data.measurements_rt,own,dt)
        if estimate is not None:
            ctx.publish("target",estimate,frame_id="map",simulation_tick=armor.simulation_tick)
'''

ARMOR_TEST = '''import unittest
import numpy as np
from tankbot import TargetPoseEstimate
from perception.armor_tracker import ArmorTracker


class ArmorContractTest(unittest.TestCase):
    def test_empty_observations_contract(self) -> None:
        mounts: np.ndarray = np.array([[1.,0.,0.],[-1.,0.,-np.pi],[0.,1.,np.pi/2],[0.,-1.,-np.pi/2]],dtype=np.float64)
        tracker: ArmorTracker = ArmorTracker(mounts,np.eye(2,dtype=np.float64))
        result: TargetPoseEstimate | None = tracker.update(np.empty((0,2),dtype=np.float64),np.zeros(3,dtype=np.float64),dt=1.0)
        if result is not None:
            self.assertIsInstance(result,TargetPoseEstimate)
            self.assertTrue(np.isfinite(np.array([result.x_m,result.y_m,result.yaw_rad])).all())
'''

POLAR_TRACKER = '''import numpy as np
from numpy.typing import NDArray
from tankbot import PolarTargetEstimate


class PolarTracker:
    def __init__(self, measurement_covariance: NDArray[np.float64]) -> None:
        self.measurement_covariance: NDArray[np.float64] = measurement_covariance
        self.estimate: PolarTargetEstimate | None = None

    def update(self, measurements: tuple[PolarTargetEstimate, ...], own_pose: NDArray[np.float64],
               dt: float) -> PolarTargetEstimate | None:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 用非线性距离/方位观测更新内部状态，对外返回车体系 (r, theta)。
        return self.estimate
'''

FUSION_TRACKER = '''import numpy as np
from numpy.typing import NDArray
from tankbot import TargetPoseEstimate
from perception.polar_tracker import PolarTracker


class FusionTracker:
    def __init__(self, gps_mount: NDArray[np.float64], radar_covariance: NDArray[np.float64],
                 gps_covariance: NDArray[np.float64]) -> None:
        self.center_tracker: PolarTracker = PolarTracker(radar_covariance)
        self.gps_mount: NDArray[np.float64] = gps_mount
        self.gps_covariance: NDArray[np.float64] = gps_covariance
        self.estimate: TargetPoseEstimate | None = None

    def update(self, measurements_rt: NDArray[np.float64], gps_xy: NDArray[np.float64],
               own_pose: NDArray[np.float64], dt: float) -> TargetPoseEstimate | None:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 联合车头 GPS 与底盘中心 Radar，估计敌车中心位置和朝向。
        return self.estimate
'''

TARGET_PREDICTION = '''import numpy as np
from numpy.typing import NDArray
from tankbot import AimInput


class TargetPredictor:
    def __init__(self, projectile_speed_mps: float, armor_mounts: NDArray[np.float64]) -> None:
        self.projectile_speed_mps: float = projectile_speed_mps
        self.armor_mounts: NDArray[np.float64] = armor_mounts
        self.previous_target: NDArray[np.float64] | None = None

    def update(self, observation: AimInput, dt: float) -> NDArray[np.float64] | None:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 预测命中点，返回当前车体系 [r, theta]；无装甲时预测中心，有装甲时再加入旋转与选点。
        return None
'''

POLAR_AUTO_AIM = '''import numpy as np
from numpy.typing import NDArray
from tankbot import AimInput, AimOutput


class AutoAim:
    def __init__(self, projectile_speed_mps: float, max_acceleration_radps2: float) -> None:
        self.projectile_speed_mps: float = projectile_speed_mps
        self.max_acceleration_radps2: float = max_acceleration_radps2

    def update(self, observation: AimInput, dt: float) -> AimOutput:
        """Algorithm input/output contract; see level guidance."""
        # TODO: observation.target_rt 是预测后的车体系 [r, theta]；输出受限角加速度和开火意图。
        return AimOutput(acceleration_radps2=0.0, fire=False)
'''

RAW_ADAPTERS = '''# TankBot raw sensor adapters. Player algorithms remain in perception/ and weapons/.
from typing import cast
import numpy as np
from numpy.typing import NDArray
from tankbot import (Module, ModuleContext, Inputs, Sample, Pose2D, RadarData, RadarDetection,
                     GpsFixData, PolarTargetEstimate, TargetPoseEstimate, AimInput, AimOutput)


def radar_matrix(sample: Sample[RadarData] | None) -> NDArray[np.float64]:
    points: NDArray[np.float64] = np.empty((len(sample.data.detections) if sample is not None else 0,2),dtype=np.float64)
    index: int
    detection: RadarDetection
    for index,detection in enumerate(sample.data.detections if sample is not None else ()):
        points[index] = [detection.range_m,detection.bearing_rad]
    return points


class PolarTrackingModule(Module):
    scaffold_api: str = "polar_tuple@1"

    def setup(self, ctx: ModuleContext) -> None:
        from perception.polar_tracker import PolarTracker
        self.tracker: PolarTracker = PolarTracker(np.array(ctx.config["observations"]["radar_covariance"],dtype=np.float64))
        self.last_tick: int | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None",inputs.latest("self_pose"))
        radar: Sample[RadarData] | None = cast("Sample[RadarData] | None",inputs.latest("radar"))
        if pose is None or radar is None or pose.simulation_tick!=radar.simulation_tick or radar.simulation_tick==self.last_tick:
            return
        dt: float = (radar.simulation_tick-self.last_tick)*ctx.config["lesson"]["tick_duration_s"] if self.last_tick is not None else ctx.dt_seconds
        self.last_tick = radar.simulation_tick
        own: NDArray[np.float64] = np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64)
        measurements: tuple[PolarTargetEstimate, ...] = tuple(PolarTargetEstimate(detection.range_m,detection.bearing_rad) for detection in radar.data.detections)
        estimate: PolarTargetEstimate | None = self.tracker.update(measurements,own,dt)
        if estimate is not None:
            ctx.publish("target",estimate,frame_id="base_link",simulation_tick=radar.simulation_tick)


class FusionTrackingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from perception.fusion_tracker import FusionTracker
        calibration: dict = dict(ctx.config["observations"])
        self.tracker: FusionTracker = FusionTracker(np.array(calibration["gps_mount"],dtype=np.float64),np.array(calibration["radar_covariance"],dtype=np.float64),np.array(calibration["gps_covariance"],dtype=np.float64))
        self.last_tick: int | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None",inputs.latest("self_pose"))
        radar: Sample[RadarData] | None = cast("Sample[RadarData] | None",inputs.latest("radar"))
        gps: Sample[GpsFixData] | None = cast("Sample[GpsFixData] | None",inputs.latest("gps"))
        if pose is None or radar is None or gps is None or len({pose.simulation_tick,radar.simulation_tick,gps.simulation_tick})!=1 or radar.simulation_tick==self.last_tick:
            return
        dt: float = (radar.simulation_tick-self.last_tick)*ctx.config["lesson"]["tick_duration_s"] if self.last_tick is not None else ctx.dt_seconds
        self.last_tick = radar.simulation_tick
        own: NDArray[np.float64] = np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64)
        estimate: TargetPoseEstimate | None = self.tracker.update(radar_matrix(radar),gps.data.positions_m,own,dt)
        if estimate is not None:
            ctx.publish("target",estimate,frame_id="map",simulation_tick=radar.simulation_tick)
'''

PREDICTIVE_ADAPTER = '''# TankBot prediction/control composition; numerical logic is player-owned.
from typing import cast
import numpy as np
from numpy.typing import NDArray
from tankbot import (Module, ModuleContext, Inputs, Sample, Pose2D, JointState, WeaponState,
                     TargetPoseEstimate, PolarTargetEstimate, AimInput, AimOutput, TurretAcceleration)


class PredictiveAimingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from weapons.target_prediction import TargetPredictor
        from weapons.auto_aim import AutoAim
        params: dict = dict(ctx.config["actuators"])
        self.predictor: TargetPredictor = TargetPredictor(params["projectile_speed_mps"],np.array(params["armor_mounts"],dtype=np.float64).reshape((-1,3)))
        self.controller: AutoAim = AutoAim(params["projectile_speed_mps"],params["max_acceleration_radps2"])
        self.public_poses: dict[int, Pose2D] = {}

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None",inputs.latest("self_pose"))
        target: Sample[TargetPoseEstimate | PolarTargetEstimate] | None = cast("Sample[TargetPoseEstimate | PolarTargetEstimate] | None",inputs.latest("target"))
        turret: Sample[JointState] | None = cast("Sample[JointState] | None",inputs.latest("turret"))
        weapon: Sample[WeaponState] | None = cast("Sample[WeaponState] | None",inputs.latest("weapon"))
        if pose is None or turret is None or weapon is None:
            return
        self.public_poses[pose.simulation_tick] = pose.data
        cutoff: int = ctx.simulation_tick-ctx.config["lesson"]["estimate_history_ticks"]
        self.public_poses = {tick:value for tick,value in self.public_poses.items() if tick>=cutoff}
        point: NDArray[np.float64] | None = None
        yaw: float | None = None
        if target is not None:
            if isinstance(target.data,PolarTargetEstimate):
                # A delayed base_link estimate belongs to its sampling pose, not today's pose.
                sampled_pose: Pose2D | None = self.public_poses.get(target.simulation_tick)
                if sampled_pose is not None:
                    angle: float = sampled_pose.yaw_rad+target.data.bearing_rad
                    point = np.array([sampled_pose.x_m,sampled_pose.y_m],dtype=np.float64)+target.data.range_m*np.array([np.cos(angle),np.sin(angle)],dtype=np.float64)
            else:
                point = np.array([target.data.x_m,target.data.y_m],dtype=np.float64)
                yaw = target.data.yaw_rad
        observation: AimInput = AimInput(
            point,
            (ctx.output_commit_tick-target.simulation_tick)*ctx.config["lesson"]["tick_duration_s"] if target is not None else 0.0,
            np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64),
            turret.data.position[0],turret.data.velocity[0],weapon.data.ready,yaw)
        prediction: NDArray[np.float64] | None = self.predictor.update(observation,ctx.dt_seconds)
        control: AimInput = observation.with_target_polar(prediction) if prediction is not None else AimInput(None,0.0,observation.own_pose,observation.turret_angle_rad,observation.turret_rate_radps,observation.weapon_ready)
        result: AimOutput = self.controller.update(control,ctx.dt_seconds)
        if not isinstance(result,AimOutput) or not isinstance(result.fire,(bool,np.bool_)):
            raise TypeError("控制器必须返回 AimOutput")
        ctx.publish("acceleration",TurretAcceleration(result.acceleration_radps2),frame_id="base_link")
        if prediction is not None and result.fire and weapon.data.ready:
            ctx.fire("fire")
'''

POLAR_TEST = '''import unittest
import numpy as np
from tankbot import PolarTargetEstimate
from perception.polar_tracker import PolarTracker


class PolarContractTest(unittest.TestCase):
    def test_empty_measurements_contract(self) -> None:
        tracker: PolarTracker = PolarTracker(np.eye(2,dtype=np.float64))
        result: PolarTargetEstimate | None = tracker.update((),np.zeros(3,dtype=np.float64),dt=1.0)
        if result is not None:
            self.assertIsInstance(result,PolarTargetEstimate)
            self.assertGreaterEqual(result.range_m,0.0)
            self.assertTrue(np.isfinite(result.bearing_rad))
'''

FUSION_TEST = '''import unittest
import numpy as np
from tankbot import TargetPoseEstimate
from perception.fusion_tracker import FusionTracker


class FusionContractTest(unittest.TestCase):
    def test_empty_observations_contract(self) -> None:
        tracker: FusionTracker = FusionTracker(np.array([1.0,0.0],dtype=np.float64),np.eye(2,dtype=np.float64),np.eye(2,dtype=np.float64))
        result: TargetPoseEstimate | None = tracker.update(np.empty((0,2),dtype=np.float64),np.empty((0,2),dtype=np.float64),np.zeros(3,dtype=np.float64),dt=1.0)
        if result is not None:
            self.assertIsInstance(result,TargetPoseEstimate)
            self.assertTrue(np.isfinite(np.array([result.x_m,result.y_m,result.yaw_rad])).all())
'''

PREDICTIVE_TEST = '''import unittest
import numpy as np
from tankbot import AimInput, AimOutput
from weapons.target_prediction import TargetPredictor
from weapons.auto_aim import AutoAim


class PredictiveContractTest(unittest.TestCase):
    def test_no_target_predictor_and_controller(self) -> None:
        observation: AimInput = AimInput(None,0.0,np.zeros(3,dtype=np.float64),0.0,0.0,True)
        predictor: TargetPredictor = TargetPredictor(1.0,np.array([[1.0,0.0,0.0]],dtype=np.float64))
        self.assertIsNone(predictor.update(observation,dt=1.0))
        controller: AutoAim = AutoAim(1.0,1.0)
        result: AimOutput = controller.update(observation,dt=1.0)
        self.assertIsInstance(result,AimOutput)
        self.assertFalse(result.fire)
        self.assertTrue(np.isfinite(result.acceleration_radps2))
'''
