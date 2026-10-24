import math
from typing import cast
from tankbot import Inputs, JointState, Module, ModuleContext, Pose2D, Sample
from .kinematics import body_increment


class Odometry(Module):
    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.x: float = ctx.config["initial_pose"][0]
        self.y: float = ctx.config["initial_pose"][1]
        self.yaw: float = ctx.config["initial_pose"][2]
        self.previous: tuple[float, ...] | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        # Deliberate faults are used only by the trusted acceptance harness.
        fault: str = ctx.config["module"]["fault"]
        if fault == "infinite_loop":
            while True:
                pass
        if fault == "exception":
            raise RuntimeError("Acceptance fixture")
        joint: Sample[JointState] | None = cast("Sample[JointState] | None", inputs.latest("wheels"))
        if joint is None:
            return
        current: tuple[float, ...] = joint.data.position
        previous: tuple[float, ...] = self.previous or tuple(0.0 for _ in current)
        increment: tuple[float, float, float] = body_increment(joint.data.name, [a-b for a, b in zip(current, previous)], ctx.config["wheels"])
        dx: float = increment[0]
        dy: float = increment[1]
        da: float = increment[2]
        angle: float = self.yaw + da/2
        self.x += math.cos(angle)*dx - math.sin(angle)*dy
        self.y += math.sin(angle)*dx + math.cos(angle)*dy
        self.yaw = (self.yaw+da+math.pi) % (2*math.pi) - math.pi
        self.previous = current
        if fault == "no_output":
            return
        covariance: tuple[float, ...] | None = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0) if fault == "bad_covariance" else None
        ctx.publish("pose", Pose2D(self.x+ctx.config["module"]["pose_offset_m"], self.y, self.yaw, covariance),
                    frame_id=ctx.config["module"]["output_frame"], simulation_tick=joint.simulation_tick)
