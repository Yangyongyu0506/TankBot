# TankBot raw sensor adapters. Player algorithms remain in perception/ and weapons/.
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
