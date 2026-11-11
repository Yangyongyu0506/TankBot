"""Immutable, authorized observations for local navigation (no simulator handles)."""
from dataclasses import dataclass
import math
import numpy as np
from numpy.typing import NDArray
from . import Twist
from .paths import readonly_path


def immutable_array(value, dtype, shape):
    array = np.asarray(value, dtype=dtype)
    if array.shape != shape or (array.dtype.kind == 'f' and not np.isfinite(array).all()):
        raise ValueError(f'Expected finite {dtype} array with shape={shape}')
    return np.frombuffer(array.tobytes(), dtype=dtype).reshape(shape)


@dataclass(frozen=True)
class Scan2D:
    """Instantaneous base_link scan; sample_tick is the original physics tick."""
    ranges_m: NDArray[np.float64]
    hit_mask: NDArray[np.bool_]
    angle_min_rad: float
    angle_increment_rad: float
    range_min_m: float
    range_max_m: float
    noise_stddev_m: float
    sample_tick: int

    def __post_init__(self) -> None:
        size = len(self.ranges_m)
        if not 1 <= size <= 180 or type(self.sample_tick) is not int or self.sample_tick < 0:
            raise ValueError('Scan2D capacity/sample_tick invalid')
        scalars = (self.angle_min_rad, self.angle_increment_rad, self.range_min_m,
                   self.range_max_m, self.noise_stddev_m)
        if (not all(math.isfinite(x) for x in scalars) or self.angle_increment_rad <= 0
                or not 0 < self.range_min_m < self.range_max_m or self.noise_stddev_m < 0):
            raise ValueError('Scan2D angles/range/noise invalid')
        ranges = immutable_array(self.ranges_m, np.float64, (size,))
        if np.any(ranges < self.range_min_m) or np.any(ranges > self.range_max_m):
            raise ValueError('Scan2D ranges outside limits')
        mask = immutable_array(self.hit_mask, np.bool_, (size,))
        if np.any(ranges[~mask] != self.range_max_m):
            raise ValueError('No-return rays must equal range_max_m')
        object.__setattr__(self, 'ranges_m', ranges)
        object.__setattr__(self, 'hit_mask', mask)

    @property
    def angles_rad(self) -> NDArray[np.float64]:
        values = self.angle_min_rad+np.arange(len(self.ranges_m))*self.angle_increment_rad
        return immutable_array(values, np.float64, values.shape)


@dataclass(frozen=True)
class LocalControlInput:
    estimated_pose: NDArray[np.float64]
    reference_path: NDArray[np.float64]
    scan: Scan2D
    nominal_command: Twist
    pose_age_s: float
    scan_age_s: float
    wheel_rates_radps: NDArray[np.float64]
    wheel_age_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, 'estimated_pose', immutable_array(self.estimated_pose, np.float64, (3,)))
        object.__setattr__(self, 'reference_path', readonly_path(self.reference_path))
        object.__setattr__(self, 'wheel_rates_radps', immutable_array(self.wheel_rates_radps, np.float64, (2,)))
        if any(not math.isfinite(age) or age < 0 for age in (self.pose_age_s, self.scan_age_s, self.wheel_age_s)):
            raise ValueError('Observation ages must be finite nonnegative simulation seconds')


@dataclass(frozen=True)
class LocalControlFeedback:
    """Algorithm command diagnostics, never measured velocity or private geometry."""
    nominal_vx_mps: float
    nominal_wz_radps: float
    final_vx_mps: float
    final_wz_radps: float
    pose_age_s: float | None
    scan_age_s: float | None
    wheel_age_s: float | None
    protection: str
