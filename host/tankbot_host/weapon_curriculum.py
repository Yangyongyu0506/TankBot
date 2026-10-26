"""Reusable raw-observation and prediction scaffolds. No executable level plugins."""

POLAR_TRACKER = '''import numpy as np
from numpy.typing import NDArray
from tankbot import PolarTargetEstimate


class PolarTracker:
    def __init__(self, measurement_covariance: NDArray[np.float64]) -> None:
        self.measurement_covariance: NDArray[np.float64] = measurement_covariance
        self.estimate: PolarTargetEstimate | None = None

    def update(self, measurements_rt: NDArray[np.float64], own_pose: NDArray[np.float64],
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
        # TODO: 跟踪目标平移/旋转，选择装甲并预测命中点，返回当前车体系 [r, theta]。
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
        estimate: PolarTargetEstimate | None = self.tracker.update(radar_matrix(radar),own,dt)
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
                     TargetPoseEstimate, AimInput, AimOutput, TurretAcceleration)


class PredictiveAimingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from weapons.target_prediction import TargetPredictor
        from weapons.auto_aim import AutoAim
        params: dict = dict(ctx.config["actuators"])
        self.predictor: TargetPredictor = TargetPredictor(params["projectile_speed_mps"],np.array(params["armor_mounts"],dtype=np.float64))
        self.controller: AutoAim = AutoAim(params["projectile_speed_mps"],params["max_acceleration_radps2"])

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None",inputs.latest("self_pose"))
        target: Sample[TargetPoseEstimate] | None = cast("Sample[TargetPoseEstimate] | None",inputs.latest("target"))
        turret: Sample[JointState] | None = cast("Sample[JointState] | None",inputs.latest("turret"))
        weapon: Sample[WeaponState] | None = cast("Sample[WeaponState] | None",inputs.latest("weapon"))
        if pose is None or turret is None or weapon is None:
            return
        observation: AimInput = AimInput(
            np.array([target.data.x_m,target.data.y_m],dtype=np.float64) if target is not None else None,
            (ctx.output_commit_tick-target.simulation_tick)*ctx.config["lesson"]["tick_duration_s"] if target is not None else 0.0,
            np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64),
            turret.data.position[0],turret.data.velocity[0],weapon.data.ready,target.data.yaw_rad if target is not None else None)
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
        result: PolarTargetEstimate | None = tracker.update(np.empty((0,2),dtype=np.float64),np.zeros(3,dtype=np.float64),dt=1.0)
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
