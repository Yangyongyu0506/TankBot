# TankBot prediction/control composition; numerical logic is player-owned.
from typing import cast
import numpy as np
from numpy.typing import NDArray
from tankbot import (Module, ModuleContext, Inputs, Sample, Pose2D, JointState, WeaponState,
                     TargetPoseEstimate, PolarTargetEstimate, AimInput, AimOutput, TurretAcceleration)


class PredictiveAimingModule(Module):
    def setup(self, ctx: ModuleContext) -> None:
        from weapons.target_prediction import TargetPredictor
        from weapons.auto_aim import AutoAim
        params: dict = dict(ctx.config["actuators"])
        self.predictor: TargetPredictor = TargetPredictor(params["projectile_speed_mps"],np.array(params["armor_mounts"],dtype=np.float64).reshape((-1,3)))
        self.controller: AutoAim = AutoAim(params["projectile_speed_mps"],params["max_acceleration_radps2"])
        self.public_poses: dict[int, Pose2D] = {}

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None",inputs.latest("self_pose"))
        target: Sample[TargetPoseEstimate | PolarTargetEstimate] | None = cast("Sample[TargetPoseEstimate | PolarTargetEstimate] | None",inputs.latest("target"))
        turret: Sample[JointState] | None = cast("Sample[JointState] | None",inputs.latest("turret"))
        weapon: Sample[WeaponState] | None = cast("Sample[WeaponState] | None",inputs.latest("weapon"))
        if pose is None or turret is None or weapon is None:
            return
        self.public_poses[pose.simulation_tick] = pose.data
        cutoff: int = ctx.simulation_tick-ctx.config["lesson"]["estimate_history_ticks"]
        self.public_poses = {tick:value for tick,value in self.public_poses.items() if tick>=cutoff}
        point: NDArray[np.float64] | None = None
        yaw: float | None = None
        if target is not None:
            if isinstance(target.data,PolarTargetEstimate):
                # A delayed base_link estimate belongs to its sampling pose, not today's pose.
                sampled_pose: Pose2D | None = self.public_poses.get(target.simulation_tick)
                if sampled_pose is not None:
                    angle: float = sampled_pose.yaw_rad+target.data.bearing_rad
                    point = np.array([sampled_pose.x_m,sampled_pose.y_m],dtype=np.float64)+target.data.range_m*np.array([np.cos(angle),np.sin(angle)],dtype=np.float64)
            else:
                point = np.array([target.data.x_m,target.data.y_m],dtype=np.float64)
                yaw = target.data.yaw_rad
        observation: AimInput = AimInput(
            point,
            (ctx.output_commit_tick-target.simulation_tick)*ctx.config["lesson"]["tick_duration_s"] if target is not None else 0.0,
            np.array([pose.data.x_m,pose.data.y_m,pose.data.yaw_rad],dtype=np.float64),
            turret.data.position[0],turret.data.velocity[0],weapon.data.ready,yaw)
        prediction: NDArray[np.float64] | None = self.predictor.update(observation,ctx.dt_seconds)
        control: AimInput = observation.with_target_polar(prediction) if prediction is not None else AimInput(None,0.0,observation.own_pose,observation.turret_angle_rad,observation.turret_rate_radps,observation.weapon_ready)
        result: AimOutput = self.controller.update(control,ctx.dt_seconds)
        if not isinstance(result,AimOutput) or not isinstance(result.fire,(bool,np.bool_)):
            raise TypeError("控制器必须返回 AimOutput")
        ctx.publish("acceleration",TurretAcceleration(result.acceleration_radps2),frame_id="base_link")
        if prediction is not None and result.fire and weapon.data.ready:
            ctx.fire("fire")
