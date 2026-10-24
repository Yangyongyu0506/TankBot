"""NumPy helpers for teaching homogeneous transforms; no World or Authority access."""
import math
import numpy as np
from numpy.typing import NDArray
from tankbot import RadarDetection


def validate_se3(matrix: NDArray[np.float64], *, tolerance: float) -> NDArray[np.float64]:
    """Check shape, finite values, SO(3) rotation and the homogeneous last row."""
    if not isinstance(matrix, np.ndarray):
        raise TypeError("radar_to_map 必须返回 numpy.ndarray，不能返回 list 或 TargetEstimate")
    if matrix.shape != (4, 4) or matrix.dtype.kind not in "fiu":
        raise ValueError("radar_to_map 需要形状 (4, 4) 的实数 SE(3) 矩阵")
    result: NDArray[np.float64] = np.asarray(matrix, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError("SE(3) 矩阵不能含 NaN 或 Infinity")
    rotation: NDArray[np.float64] = result[:3, :3]
    if (not np.allclose(result[3], [0, 0, 0, 1], atol=tolerance, rtol=0)
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=tolerance, rtol=0)
            or abs(float(np.linalg.det(rotation))-1.0) > tolerance):
        raise ValueError("SE(3) 要求最后一行 [0,0,0,1]，旋转满足 R.T @ R = I 且 det(R) = +1")
    return result


def radar_point(detection: RadarDetection) -> NDArray[np.float64]:
    """Radar observation as a homogeneous column vector [x, y, 0, 1]."""
    x_m: float = detection.range_m * math.cos(detection.bearing_rad)
    y_m: float = detection.range_m * math.sin(detection.bearing_rad)
    return np.array([x_m, y_m, 0.0, 1.0], dtype=np.float64)
