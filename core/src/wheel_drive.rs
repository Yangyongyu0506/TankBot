//! Reduced DC motors at the wheel shafts, coupled to the existing rigid body.
use crate::{BodyConfig, Chassis, Wheels};
use rapier2d_f64::prelude::*;
use serde::Deserialize;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WheelDriveConfig {
    pub model: String,
    pub resistance_ohm: f64,
    pub torque_constant_nm_per_a: f64,
    pub back_emf_v_s_per_rad: f64,
    pub wheel_inertia_kg_m2: f64,
    pub max_voltage_v: f64,
    pub command_timeout_s: f64,
}

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WheelVoltageTarget {
    pub left_voltage_v: f64,
    pub right_voltage_v: f64,
    pub source_tick: u64,
}

impl WheelDriveConfig {
    pub fn validate(&self) -> Result<(), String> {
        if self.model != "dc_wheel_voltage@1"
            || [
                self.resistance_ohm,
                self.torque_constant_nm_per_a,
                self.back_emf_v_s_per_rad,
                self.wheel_inertia_kg_m2,
                self.max_voltage_v,
                self.command_timeout_s,
            ]
            .iter()
            .any(|v| !v.is_finite() || *v <= 0.0)
        {
            return Err("Invalid DC wheel drive model".into());
        }
        Ok(())
    }

    pub fn torques(&self, voltage: [f64; 2], rates: &[f64]) -> [f64; 2] {
        std::array::from_fn(|i| {
            self.torque_constant_nm_per_a
                * (voltage[i].clamp(-self.max_voltage_v, self.max_voltage_v)
                    - self.back_emf_v_s_per_rad * rates[i])
                / self.resistance_ohm
        })
    }

    pub fn apply(
        &self,
        world: &mut PhysicsWorld,
        tank: RigidBodyHandle,
        body: &BodyConfig,
        chassis: &Chassis,
        wheels: &Wheels,
        voltage: [f64; 2],
    ) {
        let b = &world.bodies[tank];
        let velocity = b.rotation().inverse() * b.linvel();
        let wz = b.angvel();
        let rates = wheels.rates([velocity.x, velocity.y, wz], false);
        let [left, right] = self.torques(voltage, &rates);
        let r = wheels.radius_m;
        let track = wheels.differential_track_m;
        let reflected_mass = 2.0 * self.wheel_inertia_kg_m2 / (r * r);
        let reflected_inertia = self.wheel_inertia_kg_m2 * track * track / (2.0 * r * r);
        // Solve wheel inertia reactions in the longitudinal/yaw equations; do not
        // change hull mass, set a desired velocity, or retain a second wheel pose.
        let fx = body.mass_kg / (body.mass_kg + reflected_mass)
            * ((left + right) / r
                - chassis.drag_x_n_s_per_m * velocity.x
                - reflected_mass * wz * velocity.y);
        let torque = body.yaw_inertia_kg_m2 / (body.yaw_inertia_kg_m2 + reflected_inertia)
            * (track * (right - left) / (2.0 * r) - chassis.drag_yaw_nm_s * wz);
        let force = *b.rotation() * Vector::new(fx, -chassis.drag_y_n_s_per_m * velocity.y);
        let b = &mut world.bodies[tank];
        b.reset_forces(false);
        b.reset_torques(false);
        b.add_force(force, true);
        b.add_torque(torque, true);
    }
}
