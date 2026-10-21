import math
from tankbot import Module, Pose2D
from .kinematics import body_increment


class Odometry(Module):
    def reset(self, ctx, reason):
        self.x, self.y, self.yaw = ctx.config["initial_pose"]
        self.previous = None

    def update(self, inputs, ctx):
        # Deliberate faults are used only by the trusted acceptance harness.
        fault = ctx.config["module"]["fault"]
        if fault == "infinite_loop":
            while True:
                pass
        if fault == "exception":
            raise RuntimeError("Acceptance fixture")
        joint = inputs.latest("wheels")
        current = joint.data.position
        previous = self.previous or tuple(0.0 for _ in current)
        dx, dy, da = body_increment(joint.data.name, [a-b for a, b in zip(current, previous)], ctx.config["wheels"])
        angle = self.yaw + da/2
        self.x += math.cos(angle)*dx - math.sin(angle)*dy
        self.y += math.sin(angle)*dx + math.cos(angle)*dy
        self.yaw = (self.yaw+da+math.pi) % (2*math.pi) - math.pi
        self.previous = current
        if fault == "no_output":
            return
        covariance = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0) if fault == "bad_covariance" else None
        ctx.publish("pose", Pose2D(self.x+ctx.config["module"]["pose_offset_m"], self.y, self.yaw, covariance),
                    frame_id=ctx.config["module"]["output_frame"], simulation_tick=joint.simulation_tick)
