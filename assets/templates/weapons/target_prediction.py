import numpy as np
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
