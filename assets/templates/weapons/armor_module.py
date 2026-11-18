# TankBot armor observation adapter; estimation is player-owned.
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
