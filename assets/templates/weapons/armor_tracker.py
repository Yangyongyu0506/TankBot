import numpy as np
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
