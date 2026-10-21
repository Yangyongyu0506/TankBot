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
        Ok(())
    }

    pub fn revoke(&mut self) {
        self.target = None;
    }

    /// Call after chassis forces have been reset and before each physics substep.
    pub fn apply_servo(&self, world: &mut PhysicsWorld, tank: RigidBodyHandle, tick: u64, hz: u64) {
        let relative_rate = world.bodies[self.body].angvel() - world.bodies[tank].angvel();
        let goal = self
            .target
            .filter(|t| (tick - t.source_tick) as f64 / (hz as f64) < self.config.cmd_vel_timeout_s)
            .map(|t| t.velocity_radps)
            .unwrap_or(0.0);
        let torque = (self.config.yaw_inertia_kg_m2 * (goal - relative_rate) / self.config.tau_s)
            .clamp(-self.config.max_torque_nm, self.config.max_torque_nm)
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
