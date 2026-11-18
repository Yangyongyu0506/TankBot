import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D
import math


def radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:
    """Algorithm input/output contract; see level guidance."""
    T_map_radar: NDArray[np.float64] = np.eye(4, dtype=np.float64)
    # TODO: 填写旋转和位移。完成后把下一行替换成 return T_map_radar。
    raise NotImplementedError("请完成 perception/transforms.py 中的 SE(3) 矩阵")
