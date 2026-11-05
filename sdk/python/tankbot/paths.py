"""Public static reference arrays; no simulator or evaluation access."""
from typing import Any
import numpy as np
from numpy.typing import NDArray


def readonly_path(points: Any) -> NDArray[np.float64]:
    """Validate map-frame [x,y] rows and return an immutable float64 (N,2) array."""
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2 or len(array) < 2 or not np.isfinite(array).all():
        raise ValueError("路径须为有限float64 (N,2)，N至少为2")
    if np.any(np.linalg.norm(np.diff(array, axis=0), axis=1) == 0):
        raise ValueError("路径不能有连续重复点")
    return np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)
