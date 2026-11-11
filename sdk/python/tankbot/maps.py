"""Immutable, explicitly public static maps; no planning or simulator access."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
import numpy as np
from numpy.typing import NDArray


def readonly_xy(value) -> NDArray[np.float64]:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (2,) or not np.isfinite(array).all():
        raise ValueError("坐标必须为有限float64 (2,)地图系[x,y]")
    return np.frombuffer(array.tobytes(), dtype=np.float64)


@dataclass(frozen=True)
class OccupancyGrid:
    """grid[row,col]: bool; +row is map +y, +col is +x; origin is lower-left."""
    grid: NDArray[np.bool_]
    origin_xy: NDArray[np.float64]
    resolution_m: float

    def __post_init__(self) -> None:
        array = np.asarray(self.grid)
        if array.dtype != np.bool_ or array.ndim != 2 or min(array.shape) < 1:
            raise TypeError("OccupancyGrid.grid必须是非空bool (H,W) NumPy数组")
        if isinstance(self.resolution_m, bool) or not np.isfinite(self.resolution_m) or self.resolution_m <= 0:
            raise ValueError("resolution_m必须为正有限米数")
        object.__setattr__(self, "grid", np.frombuffer(array.tobytes(), dtype=np.bool_).reshape(array.shape))
        object.__setattr__(self, "origin_xy", readonly_xy(self.origin_xy))
        object.__setattr__(self, "resolution_m", float(self.resolution_m))

    def world_to_grid(self, position_xy: NDArray[np.float64]) -> tuple[int, int]:
        """Map absolute [x,y] metres -> (row,col), floor; outside raises IndexError."""
        point = readonly_xy(position_xy)
        # Decimal text avoids turning an exact public cell boundary into the
        # previous cell through binary subtraction; no epsilon or clamping.
        indices = [int(((Decimal(str(float(x)))-Decimal(str(float(o)))) /
                        Decimal(str(self.resolution_m))).to_integral_value(rounding=ROUND_FLOOR))
                   for x, o in zip(point, self.origin_xy)]
        col, row = indices
        self._check(row, col)
        return row, col

    def _check(self, row: int, col: int) -> None:
        if (isinstance(row, (bool, np.bool_)) or isinstance(col, (bool, np.bool_))
                or not isinstance(row, (int, np.integer)) or not isinstance(col, (int, np.integer))):
            raise TypeError("row/col必须为整数")
        if not (0 <= row < self.grid.shape[0] and 0 <= col < self.grid.shape[1]):
            raise IndexError(f"GRID_OUT_OF_BOUNDS: row={row}, col={col}, shape={self.grid.shape}")

    def grid_to_world(self, row: int, col: int) -> NDArray[np.float64]:
        """Return the immutable float64 map-frame centre of (row,col)."""
        self._check(row, col)
        return readonly_xy(self.origin_xy + np.array([col+.5, row+.5])*self.resolution_m)
