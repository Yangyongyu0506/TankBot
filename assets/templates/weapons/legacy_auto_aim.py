import numpy as np
from numpy.typing import NDArray
from tankbot import AimInput, AimOutput


class AutoAim:
    def __init__(self, projectile_speed_mps: float, max_acceleration_radps2: float) -> None:
        self.projectile_speed_mps: float = projectile_speed_mps
        self.max_acceleration_radps2: float = max_acceleration_radps2
        self.previous_target: NDArray[np.float64] | None = None

    def update(self, observation: AimInput, dt: float) -> AimOutput:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 实现转向、制动、运动预测与开火条件。零输出可以先部署观察。
        return AimOutput(acceleration_radps2=0.0, fire=False)
