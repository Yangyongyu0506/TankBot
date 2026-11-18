from tankbot import TargetEstimate


class Tracker:
    def __init__(self) -> None:
        # self.estimate 在 update 调用之间保留，部署或重试时重新初始化。
        self.estimate: TargetEstimate | None = None

    def update(self, measurements: tuple[TargetEstimate, ...], dt: float) -> TargetEstimate | None:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 减少抖动，并为没有测量的时刻保留合理的状态。
        return self.estimate
