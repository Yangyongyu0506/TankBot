# TankBot managed scaffold 1.2.0 — 算法只需填写 perception/ 中的 TODO。
from __future__ import annotations
from typing import TYPE_CHECKING, cast
import numpy as np
from numpy.typing import NDArray
from tankbot import Inputs, Module, ModuleContext, Pose2D, RadarData, RadarDetection, Sample, TargetEstimate
from tankbot.transforms import radar_point, validate_se3

if TYPE_CHECKING:
    from perception.tracker import Tracker


class CampaignRobot(Module):
    def setup(self, ctx: ModuleContext) -> None:
        self.tracker: Tracker | None = None
        self.last_sample: int | None = None
        if ctx.config["lesson"]["processing"] == "track":
            from perception.tracker import Tracker
            self.tracker = Tracker()

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        processing: str = ctx.config["lesson"]["processing"]
        if processing == "passive":
            return
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None", inputs.latest("self_pose"))
        radar: Sample[RadarData] | None = cast("Sample[RadarData] | None", inputs.latest("radar"))
        if pose is None or radar is None or radar.simulation_tick == self.last_sample:
            return
        self.last_sample = radar.simulation_tick
        from perception.transforms import radar_to_map
        try:
            transform: NDArray[np.float64] = validate_se3(radar_to_map(pose.data), tolerance=ctx.config["lesson"]["transform_tolerance"])
        except NotImplementedError:
            return  # 等待玩家完成矩阵函数；正式测试会给出具体 TODO 提示。
        points_list: list[TargetEstimate] = []
        hit: RadarDetection
        for hit in radar.data.detections:
            point_radar: NDArray[np.float64] = radar_point(hit)
            point_map: NDArray[np.float64] = transform @ point_radar
            point: TargetEstimate = TargetEstimate(x_m=float(point_map[0]), y_m=float(point_map[1]))
            points_list.append(point)
        points: tuple[TargetEstimate, ...] = tuple(points_list)
        estimate: TargetEstimate | None = (points[0] if points else None) if self.tracker is None else self.tracker.update(points, ctx.dt_seconds)
        if estimate is not None:
            ctx.publish("target", estimate, frame_id="map", simulation_tick=radar.simulation_tick)
