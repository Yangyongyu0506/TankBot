import numpy as np
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
