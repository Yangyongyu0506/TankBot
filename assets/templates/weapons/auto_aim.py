import numpy as np
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
