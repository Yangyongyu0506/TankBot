//! Center-mounted revolute turret. Explicit servo forces, never a kinematic sprite.
use crate::{boolean, normalize_angle, number};
use rapier2d_f64::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TurretConfig {
    pub mass_kg: f64,
    pub yaw_inertia_kg_m2: f64,
    pub center_m: [f64; 2],
    pub tau_s: f64,
    pub max_torque_nm: f64,
    pub max_relative_rate_radps: f64,
    pub bearing_drag_nm_s: f64,
    pub muzzle_offset_m: [f64; 2],
    pub initial_relative_angle_rad: f64,
    pub initial_relative_rate_radps: f64,
    pub cmd_vel_timeout_s: f64,
    pub acceleration_control: Option<AccelerationConfig>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Config, GameCore};

    #[test]
    fn acceleration_motor_reaction_coasting_saturation_watchdog_and_rate_brake() {
        let mut config: Config =
            serde_json::from_str(include_str!("../tests/fixtures/default-profile.json")).unwrap();
        config.scene.walls.clear();
        config.weapons.targets.clear();
        let mut c = GameCore::new(config, "differential").unwrap();
        let t = c.turret.as_mut().unwrap();
        t.set_acceleration(
            TurretAccelerationTarget {
                acceleration_radps2: 1000.0,
                source_tick: 0,
            },
            0,
        )
        .unwrap();
        assert_eq!(t.acceleration_target.unwrap().acceleration_radps2, 25.0);
        t.apply_servo(&mut c.world, c.tank, 0, 60);
        assert_eq!(c.world.bodies[t.body].user_torque(), 2.0);
        assert_eq!(c.world.bodies[c.tank].user_torque(), -2.0);
        c.world.bodies[t.body].set_angvel(2.3, true);
        c.world.bodies[c.tank].set_angvel(0.3, true);
        t.set_acceleration(
            TurretAccelerationTarget {
                acceleration_radps2: 0.0,
                source_tick: 0,
            },
            0,
        )
        .unwrap();
        c.world.bodies[c.tank].reset_torques(true);
        t.apply_servo(&mut c.world, c.tank, 29, 60);
        assert!((c.world.bodies[t.body].user_torque() + 0.04).abs() < 1e-12); // only bearing drag
        c.world.bodies[c.tank].reset_torques(true);
        t.apply_servo(&mut c.world, c.tank, 30, 60);
        assert!((c.world.bodies[t.body].user_torque() + 1.64).abs() < 1e-12); // active watchdog brake
        assert_eq!(c.world.bodies[t.body].angvel(), 2.3); // forces never teleport velocity
        c.world.bodies[t.body].set_angvel(9.0, true);
        t.set_acceleration(
            TurretAccelerationTarget {
                acceleration_radps2: 25.0,
                source_tick: 0,
            },
            0,
        )
        .unwrap();
        c.world.bodies[c.tank].reset_torques(true);
        t.apply_servo(&mut c.world, c.tank, 0, 60);
        assert!(c.world.bodies[t.body].user_torque() < -2.0); // limited motor + physical bearing drag
        assert_eq!(c.world.bodies[t.body].angvel(), 9.0);
        assert!(
            t.set_acceleration(
                TurretAccelerationTarget {
                    acceleration_radps2: f64::NAN,
                    source_tick: 0
                },
                0
            )
            .is_err()
        );
        assert!(
            t.set_acceleration(
                TurretAccelerationTarget {
                    acceleration_radps2: 1.0,
                    source_tick: 1
                },
                0
            )
            .is_err()
        );
    }
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AccelerationConfig {
    pub max_relative_acceleration_radps2: f64,
    pub timeout_s: f64,
    pub rate_limit_braking_tau_s: f64,
}

#[derive(Clone, Copy, Deserialize, Serialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct TurretAccelerationTarget {
    pub acceleration_radps2: f64,
    pub source_tick: u64,
}

#[derive(Clone, Copy, Deserialize, Serialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct TurretTarget {
    pub velocity_radps: f64,
    pub source_tick: u64,
}

pub struct TurretSystem {
    pub body: RigidBodyHandle,
    pub config: TurretConfig,
    pub relative_angle: f64,
    target: Option<TurretTarget>,
    acceleration_target: Option<TurretAccelerationTarget>,
    previous_wrapped_angle: f64,
}

impl TurretSystem {
    pub fn new(
        world: &mut PhysicsWorld,
        tank: RigidBodyHandle,
        config: TurretConfig,
        rigid_body: &Value,
    ) -> Result<Self, String> {
        if [
            config.mass_kg,
            config.yaw_inertia_kg_m2,
            config.tau_s,
            config.max_torque_nm,
            config.max_relative_rate_radps,
            config.cmd_vel_timeout_s,
        ]
        .iter()
        .any(|x| !x.is_finite() || *x <= 0.0)
            || !config.bearing_drag_nm_s.is_finite()
            || config.bearing_drag_nm_s < 0.0
            || config.center_m != [0.0, 0.0]
        {
            return Err("Invalid/unsupported center-mounted turret profile".into());
        }
        let base = &world.bodies[tank];
        if config.acceleration_control.as_ref().is_some_and(|a| {
            [
                a.max_relative_acceleration_radps2,
                a.timeout_s,
                a.rate_limit_braking_tau_s,
            ]
            .iter()
            .any(|x| !x.is_finite() || *x <= 0.0)
        }) {
            return Err("Invalid turret acceleration profile".into());
        }
        let rb = RigidBodyBuilder::dynamic()
            .translation(base.translation())
            .rotation(base.rotation().angle() + config.initial_relative_angle_rad)
            .linvel(base.linvel())
            .angvel(base.angvel() + config.initial_relative_rate_radps)
            .additional_mass_properties(MassProperties::new(
                Vector::ZERO,
                config.mass_kg,
                config.yaw_inertia_kg_m2,
            ))
            .can_sleep(boolean(rigid_body, "can_sleep")?)
            .linear_damping(number(rigid_body, "linear_damping")?)
            .angular_damping(number(rigid_body, "angular_damping")?);
        let body = world.insert_body(rb);
        world.insert_impulse_joint(
            tank,
            body,
            RevoluteJointBuilder::new()
                .local_anchor1(Vector::ZERO)
                .local_anchor2(Vector::ZERO)
                .contacts_enabled(false),
        );
        let relative_angle = config.initial_relative_angle_rad;
        Ok(Self {
            body,
            config,
            relative_angle,
            target: None,
            acceleration_target: None,
            previous_wrapped_angle: normalize_angle(relative_angle),
        })
    }

    pub fn set_target(&mut self, target: TurretTarget, tick: u64) -> Result<(), String> {
        if !target.velocity_radps.is_finite() || target.source_tick > tick {
            return Err("Invalid turret target".into());
        }
        self.target = Some(TurretTarget {
            velocity_radps: target.velocity_radps.clamp(
                -self.config.max_relative_rate_radps,
                self.config.max_relative_rate_radps,
            ),
            ..target
        });
        self.acceleration_target = None;
        Ok(())
    }

    pub fn set_acceleration(
        &mut self,
        target: TurretAccelerationTarget,
        tick: u64,
    ) -> Result<(), String> {
        let profile = self
            .config
            .acceleration_control
            .as_ref()
            .ok_or("Acceleration profile not configured")?;
        if !target.acceleration_radps2.is_finite() || target.source_tick > tick {
            return Err("Invalid turret acceleration target".into());
        }
        self.acceleration_target = Some(TurretAccelerationTarget {
            acceleration_radps2: target.acceleration_radps2.clamp(
                -profile.max_relative_acceleration_radps2,
                profile.max_relative_acceleration_radps2,
            ),
            ..target
        });
        self.target = None;
        Ok(())
    }

    pub fn revoke(&mut self) {
        self.target = None;
        self.acceleration_target = None;
    }

    /// Call after chassis forces have been reset and before each physics substep.
    pub fn apply_servo(&self, world: &mut PhysicsWorld, tank: RigidBodyHandle, tick: u64, hz: u64) {
        let relative_rate = world.bodies[self.body].angvel() - world.bodies[tank].angvel();
        let goal = self
            .target
            .filter(|t| (tick - t.source_tick) as f64 / (hz as f64) < self.config.cmd_vel_timeout_s)
            .map(|t| t.velocity_radps)
            .unwrap_or(0.0);
        let motor = if let Some(target) = self.acceleration_target {
            let profile = self
                .config
                .acceleration_control
                .as_ref()
                .expect("Validated acceleration profile");
            let expired = (tick - target.source_tick) as f64 / hz as f64 >= profile.timeout_s;
            let overspeed = relative_rate.abs() >= self.config.max_relative_rate_radps
                && target.acceleration_radps2 * relative_rate >= 0.0;
            if expired || overspeed {
                -self.config.yaw_inertia_kg_m2 * relative_rate / profile.rate_limit_braking_tau_s
            } else {
                self.config.yaw_inertia_kg_m2 * target.acceleration_radps2
            }
        } else {
            self.config.yaw_inertia_kg_m2 * (goal - relative_rate) / self.config.tau_s
        };
        let torque = motor.clamp(-self.config.max_torque_nm, self.config.max_torque_nm)
            - self.config.bearing_drag_nm_s * relative_rate;
        let turret = &mut world.bodies[self.body];
        turret.reset_forces(true);
        turret.reset_torques(true);
        turret.add_torque(torque, true);
        world.bodies[tank].add_torque(-torque, true);
    }

    pub fn observe_angle(&mut self, world: &PhysicsWorld, tank: RigidBodyHandle) {
        let angle = normalize_angle(
            world.bodies[self.body].rotation().angle() - world.bodies[tank].rotation().angle(),
        );
        self.relative_angle += normalize_angle(angle - self.previous_wrapped_angle);
        self.previous_wrapped_angle = angle;
    }

    pub fn sample(&self, world: &PhysicsWorld, tank: RigidBodyHandle) -> Value {
        serde_json::json!({"name":["turret_joint"],"position":[self.relative_angle],
            "velocity":[world.bodies[self.body].angvel()-world.bodies[tank].angvel()],"effort":[]})
    }

    pub fn muzzle(&self, world: &PhysicsWorld) -> (Vector, Vector, Vector) {
        let turret = &world.bodies[self.body];
        let offset = Vector::new(
            self.config.muzzle_offset_m[0],
            self.config.muzzle_offset_m[1],
        );
        let point = turret.translation() + *turret.rotation() * offset;
        (
            point,
            turret.velocity_at_point(point),
            *turret.rotation() * Vector::X,
        )
    }
}
