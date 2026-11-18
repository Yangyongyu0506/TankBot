import numpy as np
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
