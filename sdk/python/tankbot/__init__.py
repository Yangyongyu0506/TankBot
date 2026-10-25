"""Typed values and synchronous module contract for the M1 local worker."""
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Generic, Mapping, TypeVar
import numpy as np
from numpy.typing import NDArray


def _covariance_matrix(value, size: int) -> NDArray[np.float64] | None:
    if value is None:
        return None
    original: np.ndarray = np.asarray(value)
    if original.dtype.kind not in "fiu":
        raise TypeError("covariance 必须包含实数，不接受复数、字符串或对象数组")
    array: NDArray[np.float64] = np.asarray(original, dtype=np.float64)
    # The JSON wire format and older saved projects use flat row-major sequences.
    if array.shape == (size * size,):
        array = array.reshape(size, size)
    if array.shape != (size, size):
        raise ValueError(f"covariance 必须是 ({size}, {size}) NumPy 矩阵")
    # Immutable byte backing prevents writable views from changing shared SDK input.
    return np.frombuffer(array.tobytes(order="C"), dtype=np.float64).reshape(size, size)


def _wire_scalars(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _wire_scalars(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_scalars(item) for item in value]
    return value


@dataclass(frozen=True)
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class Twist:
    linear: Vector3 = field(default_factory=Vector3)
    angular: Vector3 = field(default_factory=Vector3)


@dataclass(frozen=True)
class Pose2D:
    x_m: float
    y_m: float
    yaw_rad: float
    covariance: NDArray[np.float64] | None = None
    child_frame_id: str = "base_link"

    def __post_init__(self) -> None:
        object.__setattr__(self, "covariance", _covariance_matrix(self.covariance, 3))


@dataclass(frozen=True)
class EncoderData:
    left_distance_m: float
    right_distance_m: float


@dataclass(frozen=True)
class ImuData:
    angular_velocity_z_radps: float
    linear_acceleration_x_mps2: float
    linear_acceleration_y_mps2: float


@dataclass(frozen=True)
class RadarDetection:
    observation_id: str
    range_m: float
    bearing_rad: float


@dataclass(frozen=True)
class RadarData:
    detections: tuple[RadarDetection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "detections", tuple(
            RadarDetection(**item) if isinstance(item, dict) else item for item in self.detections
        ))


@dataclass(frozen=True)
class TargetEstimate:
    x_m: float
    y_m: float
    covariance: NDArray[np.float64] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "covariance", _covariance_matrix(self.covariance, 2))


@dataclass(frozen=True)
class TargetPoseEstimate:
    x_m: float
    y_m: float
    yaw_rad: float
    covariance: NDArray[np.float64] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self,"covariance",_covariance_matrix(self.covariance,3))


@dataclass(frozen=True)
class TargetPoints:
    """Current map-frame measurement matrix, shape (N, 2); never an implicit history."""
    positions_m: NDArray[np.float64]

    def __post_init__(self) -> None:
        array = np.asarray(self.positions_m,dtype=np.float64)
        if array.shape == (0,):
            array = array.reshape(0,2)
        if array.ndim != 2 or array.shape[1] != 2:
            raise ValueError("positions_m 必须是 shape=(N,2) 的数值数组")
        object.__setattr__(self,"positions_m",np.frombuffer(array.tobytes(),dtype=np.float64).reshape(array.shape))


@dataclass(frozen=True)
class TurretVelocity:
    velocity_radps: float


@dataclass(frozen=True)
class TurretAcceleration:
    acceleration_radps2: float


@dataclass(frozen=True)
class AimInput:
    target_xy: NDArray[np.float64] | None
    target_age_s: float
    own_pose: NDArray[np.float64]
    turret_angle_rad: float
    turret_rate_radps: float
    weapon_ready: bool
    target_yaw_rad: float | None = None

    def __post_init__(self) -> None:
        pose = np.asarray(self.own_pose,dtype=np.float64)
        if pose.shape != (3,):
            raise ValueError("own_pose 必须为 [x,y,yaw]，shape=(3,)")
        object.__setattr__(self,"own_pose",np.frombuffer(pose.tobytes(),dtype=np.float64))
        if self.target_xy is not None:
            target = np.asarray(self.target_xy,dtype=np.float64)
            if target.shape != (2,):
                raise ValueError("target_xy 必须为 [x,y]，shape=(2,)")
            object.__setattr__(self,"target_xy",np.frombuffer(target.tobytes(),dtype=np.float64))


@dataclass(frozen=True)
class AimOutput:
    acceleration_radps2: float
    fire: bool


@dataclass(frozen=True)
class FireCommand:
    """Single cannon shot. Use ModuleContext.fire to attach its idempotency key."""
    pass


@dataclass(frozen=True)
class FireResult:
    request_id: str
    status: str
    processed_tick: int


@dataclass(frozen=True)
class WeaponState:
    ready: bool
    cooldown_remaining_ticks: int
    shots_fired: int
    hits_received: int
    last_result: FireResult | None

    def __post_init__(self) -> None:
        if isinstance(self.last_result, dict):
            object.__setattr__(self, "last_result", FireResult(**self.last_result))


@dataclass(frozen=True)
class JointState:
    name: tuple[str, ...]
    position: tuple[float, ...]
    velocity: tuple[float, ...]
    effort: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        for key in ("name", "position", "velocity", "effort"):
            object.__setattr__(self, key, tuple(getattr(self, key)))


T = TypeVar("T")


@dataclass(frozen=True)
class Sample(Generic[T]):
    data: T
    simulation_tick: int
    frame_id: str | None
    sequence_number: int


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


class Inputs:
    def __init__(self, samples: Mapping[str, Sample[Any]]) -> None:
        self._samples: Mapping[str, Sample[Any]] = MappingProxyType(dict(samples))

    def latest(self, port: str) -> Sample[Any] | None:
        return self._samples.get(port)


class ModuleContext:
    simulation_tick: int
    dt_seconds: float
    output_commit_tick: int
    config: Mapping[str, Any]

    def __init__(self, simulation_tick: int, dt_seconds: float, output_commit_tick: int,
                 config: Mapping[str, Any]) -> None:
        self.simulation_tick: int = simulation_tick
        self.dt_seconds: float = dt_seconds
        self.output_commit_tick: int = output_commit_tick
        self.config: Mapping[str, Any] = freeze(config)
        self._outputs: list[tuple[str, str, dict[str, Any], str, int]] = []
        self._commands: list[tuple[str, str]] = []

    def publish(self, port: str, value: Any, *, frame_id: str,
                simulation_tick: int | None = None) -> None:
        types: dict[type, str] = {Pose2D: "pose2d@1", TargetEstimate: "target_estimate@1", TargetPoseEstimate:"target_pose_estimate@1", TargetPoints:"target_points@1", Twist: "twist@1", TurretVelocity: "turret_velocity@1", TurretAcceleration:"turret_acceleration@1"}
        if type(value) not in types:
            raise TypeError("Unsupported output value")
        payload: dict[str, Any] = asdict(value)
        if isinstance(value, (Pose2D, TargetEstimate, TargetPoseEstimate)) and value.covariance is not None:
            payload["covariance"] = value.covariance.ravel(order="C").tolist()
        if isinstance(value,TargetPoints):
            payload["positions_m"] = value.positions_m.tolist()
        payload = _wire_scalars(payload)
        self._outputs.append((port, types[type(value)], payload, frame_id,
                              self.simulation_tick if simulation_tick is None else simulation_tick))

    def fire(self, port: str = "fire", *, request_id: str | None = None) -> str:
        request_id = request_id if request_id is not None else f"fire-{self.simulation_tick}-{len(self._commands)}"
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("Invalid request_id")
        self._commands.append((port, request_id))
        return request_id


class Module:
    def setup(self, ctx: ModuleContext) -> None:
        pass

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        pass

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        raise NotImplementedError

    def teardown(self, ctx: ModuleContext) -> None:
        pass
