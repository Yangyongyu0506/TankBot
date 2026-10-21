"""Opt-in SDK example; existing localization files are preserved."""
from tankbot import TurretVelocity
from localization.odometry import Odometry


class WeaponDemo(Odometry):
    def update(self, inputs, ctx):
        super().update(inputs, ctx)
        settings = ctx.config["module"]["weapon_demo"]
        if not settings["enabled"]:
            return
        ctx.publish("turret_velocity", TurretVelocity(settings["turret_velocity_radps"]), frame_id="base_link")
        if ctx.simulation_tick % settings["fire_period_ticks"] == 0:
            ctx.fire(request_id=f"demo-{ctx.simulation_tick}")
