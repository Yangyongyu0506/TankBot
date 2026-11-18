import numpy as np
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
