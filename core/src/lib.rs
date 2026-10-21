//! Pure fixed-step authority. Private snapshots belong only to the trusted host.
use rapier2d_f64::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    f64::consts::{PI, TAU},
};

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BodyConfig {
    pub length_m: f64,
    pub width_m: f64,
    pub corner_radius_m: f64,
    pub mass_kg: f64,
    pub yaw_inertia_kg_m2: f64,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Servo {
    pub tau_x_s: f64,
    pub tau_y_s: f64,
    pub tau_yaw_s: f64,
    pub max_force_x_n: f64,
    pub max_force_y_n: f64,
    pub max_torque_nm: f64,
    pub zero_target_behavior: String,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Chassis {
    pub lateral_actuation: bool,
    pub drag_x_n_s_per_m: f64,
    pub drag_y_n_s_per_m: f64,
    pub drag_yaw_nm_s: f64,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Clock {
    pub physics_hz: u64,
    pub substeps: u64,
    pub sensor_hz: u64,
    pub algorithm_hz: u64,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Wheels {
    pub radius_m: f64,
    pub differential_track_m: f64,
    pub mecanum_half_length_m: f64,
    pub mecanum_half_width_m: f64,
    pub roller_angle_deg: f64,
    pub arrangement: String,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Wall {
    pub center: [f64; 2],
    pub size: [f64; 2],
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Scene {
    pub default_chassis: String,
    pub initial_pose: [f64; 3],
    pub initial_velocity: [f64; 3],
    pub public_initial_pose: bool,
    pub public_map: bool,
    pub walls: Vec<Wall>,
}
#[derive(Clone, Deserialize)]
pub struct Config {
    pub body: BodyConfig,
    pub servo: Servo,
    pub chassis: BTreeMap<String, Chassis>,
    pub clock: Clock,
    pub wheels: Wheels,
    pub scene: Scene,
    pub solver: Value,
    pub rigid_body: Value,
    pub contact: Value,
    pub controller: Value,
    pub motion_limits: Value,
}
pub fn normalize_angle(x: f64) -> f64 {
    (x + PI).rem_euclid(TAU) - PI
}
fn number(v: &Value, k: &str) -> Result<f64, String> {
    v[k].as_f64()
        .filter(|x| x.is_finite())
        .ok_or_else(|| format!("Missing/invalid {k}"))
}
fn boolean(v: &Value, k: &str) -> Result<bool, String> {
    v[k].as_bool().ok_or_else(|| format!("Missing/invalid {k}"))
}
fn complete_shape(value: &Value, shape: &Value) -> bool {
    match (value, shape) {
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && b.iter()
                    .all(|(k, v)| a.get(k).is_some_and(|x| complete_shape(x, v)))
        }
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| complete_shape(a, b))
        }
        (Value::Number(_), Value::Number(_))
        | (Value::Bool(_), Value::Bool(_))
        | (Value::String(_), Value::String(_))
        | (Value::Null, Value::Null) => true,
        _ => false,
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VelocityTarget {
    pub vx: f64,
    pub vy: f64,
    pub wz: f64,
    pub source_tick: u64,
}
#[derive(Serialize, Debug)]
pub struct PrivateSnapshot {
    pub tick: u64,
    pub simulation_time_ns: u64,
    pub truth_pose: [f64; 3],
    pub truth_velocity: [f64; 3],
    pub sensors: Option<Value>,
}

pub struct GameCore {
    world: PhysicsWorld,
    tank: RigidBodyHandle,
    config: Config,
    chassis: Chassis,
    tick: u64,
    target: Option<VelocityTarget>,
    timeout_s: f64,
    limits: [f64; 3],
    wheel_positions: Vec<f64>,
    wheel_rates: Vec<f64>,
    delta_v_body: Vector,
    angular_rate_integral: f64,
    last_sensors: Option<Value>,
}
impl GameCore {
    pub fn new(config: Config, chassis_name: &str) -> Result<Self, String> {
        let chassis = config
            .chassis
            .get(chassis_name)
            .ok_or("Unknown chassis")?
            .clone();
        let t = &config.clock;
        if t.physics_hz == 0
            || t.substeps == 0
            || t.sensor_hz == 0
            || !t.physics_hz.is_multiple_of(t.sensor_hz)
            || t.algorithm_hz == 0
            || !t.physics_hz.is_multiple_of(t.algorithm_hz)
        {
            return Err("Invalid clock ratios".into());
        }
        let b = &config.body;
        let s = &config.servo;
        if [
            b.length_m,
            b.width_m,
            b.corner_radius_m,
            b.mass_kg,
            b.yaw_inertia_kg_m2,
            s.tau_x_s,
            s.tau_y_s,
            s.tau_yaw_s,
            s.max_force_x_n,
            s.max_force_y_n,
            s.max_torque_nm,
            config.wheels.radius_m,
            config.wheels.differential_track_m,
        ]
        .iter()
        .any(|x| !x.is_finite() || *x <= 0.0)
            || 2.0 * b.corner_radius_m >= b.length_m.min(b.width_m)
            || s.zero_target_behavior != "active_brake"
            || config.wheels.arrangement != "X"
            || !config.wheels.roller_angle_deg.is_finite()
            || !(0.0..PI / 2.0).contains(&config.wheels.roller_angle_deg.to_radians())
            || config.wheels.roller_angle_deg == 0.0
        {
            return Err("Unsupported/invalid physical profile".into());
        }
        // Inspect only the required field SHAPES. Never fill in missing values from defaults.
        let shape =
            serde_json::to_value(IntegrationParameters::default()).map_err(|e| e.to_string())?;
        if !complete_shape(&config.solver, &shape) {
            return Err("Incomplete solver profile".into());
        }
        let solver: IntegrationParameters =
            serde_json::from_value(config.solver.clone()).map_err(|e| e.to_string())?;
        if solver.dt != 1.0 / (t.physics_hz * t.substeps) as f64
            || solver.num_solver_iterations == 0
            || solver.num_internal_pgs_iterations == 0
        {
            return Err("Invalid solver timestep/iterations".into());
        }
        let mut world = PhysicsWorld::new();
        world.gravity = Vector::ZERO;
        world.integration_parameters = solver;
        let p = config.scene.initial_pose;
        let v = config.scene.initial_velocity;
        let rb = RigidBodyBuilder::dynamic()
            .translation(Vector::new(p[0], p[1]))
            .rotation(p[2])
            .linvel(Rotation::from_angle(p[2]) * Vector::new(v[0], v[1]))
            .angvel(v[2])
            .can_sleep(boolean(&config.rigid_body, "can_sleep")?)
            .ccd_enabled(boolean(&config.rigid_body, "ccd_enabled")?)
            .linear_damping(number(&config.rigid_body, "linear_damping")?)
            .angular_damping(number(&config.rigid_body, "angular_damping")?);
        let f = number(&config.contact, "friction")?;
        let e = number(&config.contact, "restitution")?;
        let shape = ColliderBuilder::round_cuboid(
            b.length_m / 2.0 - b.corner_radius_m,
            b.width_m / 2.0 - b.corner_radius_m,
            b.corner_radius_m,
        )
        .mass_properties(MassProperties::new(
            Vector::ZERO,
            b.mass_kg,
            b.yaw_inertia_kg_m2,
        ))
        .friction(f)
        .restitution(e);
        let (tank, _) = world.insert(rb, shape);
        for w in &config.scene.walls {
            if w.size.iter().any(|x| !x.is_finite() || *x <= 0.0) {
                return Err("Invalid wall size".into());
            }
            world.colliders.insert(
                ColliderBuilder::cuboid(w.size[0] / 2.0, w.size[1] / 2.0)
                    .translation(Vector::new(w.center[0], w.center[1]))
                    .friction(f)
                    .restitution(e),
            );
        }
        let limits = [
            number(&config.motion_limits, "max_vx_mps")?,
            number(&config.motion_limits, "max_vy_mps")?,
            number(&config.motion_limits, "max_wz_radps")?,
        ];
        let timeout_s = number(&config.controller, "cmd_vel_timeout_s")?;
        if timeout_s <= 0.0
            || limits.iter().any(|v| *v <= 0.0)
            || config.controller["overspeed_target"] != "clamp_each_axis"
            || config.controller["unsupported_lateral"] != "reject"
            || !(0.0..=1.0).contains(&e)
            || f < 0.0
            || [
                chassis.drag_x_n_s_per_m,
                chassis.drag_y_n_s_per_m,
                chassis.drag_yaw_nm_s,
            ]
            .iter()
            .any(|x| !x.is_finite() || *x < 0.0)
            || config
                .chassis
                .get("differential")
                .is_none_or(|c| c.lateral_actuation)
            || config
                .chassis
                .get("omnidirectional")
                .is_none_or(|c| !c.lateral_actuation)
        {
            return Err("Invalid controller bounds".into());
        }
        let count = if chassis.lateral_actuation { 4 } else { 2 };
        let mut core = Self {
            world,
            tank,
            config,
            chassis,
            tick: 0,
            target: None,
            timeout_s,
            limits,
            wheel_positions: vec![0.0; count],
            wheel_rates: vec![0.0; count],
            delta_v_body: Vector::ZERO,
            angular_rate_integral: 0.0,
            last_sensors: None,
        };
        core.wheel_rates = core.rates(core.body_velocity());
        core.last_sensors = Some(core.sensor_payload(Vector::ZERO, v[2]));
        Ok(core)
    }
    fn body_velocity(&self) -> [f64; 3] {
        let b = &self.world.bodies[self.tank];
        let v = b.rotation().inverse() * b.linvel();
        [v.x, v.y, b.angvel()]
    }
    fn rates(&self, v: [f64; 3]) -> Vec<f64> {
        let w = &self.config.wheels;
        let [x, y, z] = v;
        if self.chassis.lateral_actuation {
            let beta = w.roller_angle_deg.to_radians();
            let lateral = beta.cos() / beta.sin();
            let k = w.mecanum_half_length_m * lateral + w.mecanum_half_width_m;
            vec![
                (x - lateral * y - k * z) / w.radius_m,
                (x + lateral * y + k * z) / w.radius_m,
                (x + lateral * y - k * z) / w.radius_m,
                (x - lateral * y + k * z) / w.radius_m,
            ]
        } else {
            vec![
                (x - z * w.differential_track_m / 2.0) / w.radius_m,
                (x + z * w.differential_track_m / 2.0) / w.radius_m,
            ]
        }
    }
    fn sensor_payload(&self, a: Vector, wz: f64) -> Value {
        let names = if self.chassis.lateral_actuation {
            vec!["front_left", "front_right", "rear_left", "rear_right"]
        } else {
            vec!["left", "right"]
        };
        json!({"joint_states":{"name":names,"position":self.wheel_positions,"velocity":self.wheel_rates,"effort":[]},"imu":{"angular_velocity_z_radps":wz,"linear_acceleration_x_mps2":a.x,"linear_acceleration_y_mps2":a.y}})
    }
    pub fn set_target(&mut self, t: VelocityTarget) -> Result<(), String> {
        if t.source_tick > self.tick || ![t.vx, t.vy, t.wz].iter().all(|v| v.is_finite()) {
            return Err("Invalid target".into());
        }
        if !self.chassis.lateral_actuation && t.vy != 0.0 {
            return Err("UNSUPPORTED_MOTION".into());
        }
        self.target = Some(VelocityTarget {
            vx: t.vx.clamp(-self.limits[0], self.limits[0]),
            vy: t.vy.clamp(-self.limits[1], self.limits[1]),
            wz: t.wz.clamp(-self.limits[2], self.limits[2]),
            source_tick: t.source_tick,
        });
        Ok(())
    }
    pub fn revoke_target(&mut self) {
        self.target = None;
    }
    pub fn step(&mut self) {
        let goal = self
            .target
            .filter(|t| {
                (self.tick - t.source_tick) as f64 / (self.config.clock.physics_hz as f64)
                    < self.timeout_s
            })
            .map(|t| [t.vx, t.vy, t.wz])
            .unwrap_or([0.0; 3]);
        let dt = self.world.integration_parameters.dt;
        for _ in 0..self.config.clock.substeps {
            let before = self.body_velocity();
            let rates = self.rates(before);
            let b = &mut self.world.bodies[self.tank];
            let old_v = b.linvel();
            let old_angle = b.rotation().angle();
            let s = &self.config.servo;
            let c = &self.chassis;
            let fx = (self.config.body.mass_kg * (goal[0] - before[0]) / s.tau_x_s)
                .clamp(-s.max_force_x_n, s.max_force_x_n)
                - c.drag_x_n_s_per_m * before[0];
            let fy = (if c.lateral_actuation {
                (self.config.body.mass_kg * (goal[1] - before[1]) / s.tau_y_s)
                    .clamp(-s.max_force_y_n, s.max_force_y_n)
            } else {
                0.0
            }) - c.drag_y_n_s_per_m * before[1];
            let mz = (self.config.body.yaw_inertia_kg_m2 * (goal[2] - before[2]) / s.tau_yaw_s)
                .clamp(-s.max_torque_nm, s.max_torque_nm)
                - c.drag_yaw_nm_s * before[2];
            let force = *b.rotation() * Vector::new(fx, fy);
            b.reset_forces(true);
            b.reset_torques(true);
            b.add_force(force, true);
            b.add_torque(mz, true);
            self.world.step();
            let b = &self.world.bodies[self.tank];
            let da = normalize_angle(b.rotation().angle() - old_angle);
            self.delta_v_body +=
                Rotation::from_angle(old_angle + da / 2.0).inverse() * (b.linvel() - old_v);
            self.angular_rate_integral += (before[2] + b.angvel()) * dt / 2.0;
            self.wheel_rates = self.rates(self.body_velocity());
            for (i, p) in self.wheel_positions.iter_mut().enumerate() {
                *p += (rates[i] + self.wheel_rates[i]) * dt / 2.0;
            }
        }
        self.tick += 1;
        if self
            .tick
            .is_multiple_of(self.config.clock.physics_hz / self.config.clock.sensor_hz)
        {
            let window = 1.0 / self.config.clock.sensor_hz as f64;
            self.last_sensors = Some(self.sensor_payload(
                self.delta_v_body / window,
                self.angular_rate_integral / window,
            ));
            self.delta_v_body = Vector::ZERO;
            self.angular_rate_integral = 0.0;
        } else {
            self.last_sensors = None;
        }
    }
    /// Trusted adapter only: never serialize this DTO to the robot worker or UI.
    pub fn private_snapshot(&self) -> PrivateSnapshot {
        let b = &self.world.bodies[self.tank];
        let p = b.translation();
        PrivateSnapshot {
            tick: self.tick,
            simulation_time_ns: self.tick * 1_000_000_000 / self.config.clock.physics_hz,
            truth_pose: [p.x, p.y, normalize_angle(b.rotation().angle())],
            truth_velocity: self.body_velocity(),
            sensors: self.last_sensors.clone(),
        }
    }
}
pub fn run_build_probe(text: &str) -> Result<f64, String> {
    let raw: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let config: Config = serde_json::from_value(raw.clone()).map_err(|e| e.to_string())?;
    let target: [f64; 3] = serde_json::from_value(raw["validation"]["probe_target"].clone())
        .map_err(|e| e.to_string())?;
    let ticks = raw["validation"]["ticks"]
        .as_u64()
        .ok_or("Missing probe ticks")?;
    let name = config.scene.default_chassis.clone();
    let mut c = GameCore::new(config, &name)?;
    for tick in 0..ticks {
        c.set_target(VelocityTarget {
            vx: target[0],
            vy: target[1],
            wz: target[2],
            source_tick: tick,
        })?;
        c.step();
    }
    Ok(c.private_snapshot().truth_pose[0])
}
// Trusted build probe, not the browser deployment API. Single source of physical parameters.
#[cfg(target_arch = "wasm32")]
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_m1_probe() -> f64 {
    run_build_probe(include_str!("../../config/m1.json")).expect("Invalid profile")
}
