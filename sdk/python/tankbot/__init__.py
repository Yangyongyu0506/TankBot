"""Typed values and synchronous module contract for the M1 local worker."""
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Generic, TypeVar


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
    covariance: tuple[float, ...] | None = None
    child_frame_id: str = "base_link"

    def __post_init__(self):
        if self.covariance is not None:
            object.__setattr__(self, "covariance", tuple(self.covariance))


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
class JointState:
    name: tuple[str, ...]
    position: tuple[float, ...]
    velocity: tuple[float, ...]
    effort: tuple[float, ...] = ()

    def __post_init__(self):
        for key in ("name", "position", "velocity", "effort"):
            object.__setattr__(self, key, tuple(getattr(self, key)))


T = TypeVar("T")


@dataclass(frozen=True)
class Sample(Generic[T]):
    data: T
    simulation_tick: int
    frame_id: str | None
    sequence_number: int


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


class Inputs:
    def __init__(self, samples):
        self._samples = MappingProxyType(dict(samples))

    def latest(self, port: str) -> Sample | None:
        return self._samples.get(port)


class ModuleContext:
    def __init__(self, simulation_tick, dt_seconds, output_commit_tick, config):
        self.simulation_tick = simulation_tick
        self.dt_seconds = dt_seconds
        self.output_commit_tick = output_commit_tick
        self.config = freeze(config)
        self._outputs = []

    def publish(self, port: str, value: Any, *, frame_id: str,
                simulation_tick: int | None = None) -> None:
        types = {Pose2D: "pose2d@1", Twist: "twist@1"}
        if type(value) not in types:
            raise TypeError("Unsupported output value")
        self._outputs.append((port, types[type(value)], asdict(value), frame_id,
                              self.simulation_tick if simulation_tick is None else simulation_tick))


class Module:
    def setup(self, ctx: ModuleContext) -> None:
        pass

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        pass

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        raise NotImplementedError

    def teardown(self, ctx: ModuleContext) -> None:
        pass
