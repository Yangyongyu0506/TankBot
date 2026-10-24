"""Opt-in SDK example; existing localization files are preserved."""
from typing import Any, Mapping
from tankbot import Inputs, ModuleContext, TurretVelocity
from localization.odometry import Odometry


class WeaponDemo(Odometry):
    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        super().update(inputs, ctx)
        settings: Mapping[str, Any] = ctx.config["module"]["weapon_demo"]
        if not settings["enabled"]:
            return
        ctx.publish("turret_velocity", TurretVelocity(settings["turret_velocity_radps"]), frame_id="base_link")
        if ctx.simulation_tick % settings["fire_period_ticks"] == 0:
            ctx.fire(request_id=f"demo-{ctx.simulation_tick}")
