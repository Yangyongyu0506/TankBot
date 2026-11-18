import numpy as np
from numpy.typing import NDArray
from tankbot import AimInput, AimOutput
from weapons.auto_aim import AutoAim


class ArmorAim:
    def __init__(self, projectile_speed_mps: float, max_acceleration_radps2: float,
                 armor_mounts: NDArray[np.float64]) -> None:
        self.controller: AutoAim = AutoAim(projectile_speed_mps, max_acceleration_radps2)
        # 每行是 [安装 x, 安装 y, 向外法线 yaw]，参考系为敌车底盘。
        self.armor_mounts: NDArray[np.float64] = armor_mounts

    def update(self, observation: AimInput, dt: float) -> AimOutput:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 选择可击中的装甲并计算瞄准点，然后复用/扩展 C3 控制器。
        return AimOutput(acceleration_radps2=0.0, fire=False)
