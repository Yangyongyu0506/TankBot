//! Pure fixed-step authority. Private snapshots belong only to the trusted host.
mod cannon;
mod enemy;
pub mod session;
mod turret;
#[cfg(target_arch = "wasm32")]
mod wasm;
mod wheels;
use cannon::CannonSystem;
pub use cannon::{FiringConfig, Numerics, ProjectileConfig, ShotRequest, TargetConfig};
use enemy::{EnemyTank, drive_servo};
use rapier2d_f64::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    f64::consts::{PI, TAU},
};
use turret::TurretSystem;
pub use turret::{TurretConfig, TurretTarget};
pub use wheels::Wheels;

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
    pub weapons: WeaponsConfig,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WeaponsConfig {
    pub enabled: bool,
    pub turret: TurretConfig,
    pub projectile: ProjectileConfig,
    pub firing: FiringConfig,
    pub numerics: Numerics,
    pub targets: Vec<TargetConfig>,
    pub impact: Value,
    pub collision: Value,
    pub mass_accounting: String,
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
    pub turret_state: Option<Value>,
    pub weapon_state: Option<Value>,
    pub projectiles: Value,
    pub fire_results: Value,
    pub weapon_events: Value,
    pub target_hits: Value,
    pub targets: Value,
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
    turret: Option<TurretSystem>,
    cannon: Option<CannonSystem>,
    enemies: BTreeMap<String, EnemyTank>,
    destroyed_targets: BTreeMap<String, Value>,
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
        config.wheels.validate()?;
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
        let turret = if config.weapons.enabled {
            if config.weapons.mass_accounting != "fixed_chassis_mass" {
                return Err("Unsupported weapon mass accounting".into());
            }
            Some(TurretSystem::new(
                &mut world,
                tank,
                config.weapons.turret.clone(),
                &config.rigid_body,
            )?)
        } else {
            None
        };
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
        let mut enemies = BTreeMap::new();
        let cannon = if config.weapons.enabled {
            let cannon = CannonSystem::new(&config.weapons, b, &config.scene.walls)?;
            for target in &config.weapons.targets {
                if let Some(health) = &target.health {
                    if target.motion.is_none()
                        || health.max_hp == 0
                        || health.damage_per_hit == 0
                        || health.collision_damage != 0
                        || health.death_behavior != "remove_at_substep_end"
                    {
                        return Err("Unsupported target health profile".into());
                    }
                }
                if let Some(patrol) = &target.motion {
                    enemies.insert(
                        target.target_id.clone(),
                        EnemyTank::new(&mut world, &config, target.pose, patrol.clone())?,
                    );
                    continue;
                }
                world.colliders.insert(
                    ColliderBuilder::new(cannon::body_shape(b))
                        .translation(Vector::new(target.pose[0], target.pose[1]))
                        .rotation(target.pose[2])
                        .friction(f)
                        .restitution(e),
                );
            }
            Some(cannon)
        } else {
            None
        };
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
            turret,
            cannon,
            enemies,
            destroyed_targets: BTreeMap::new(),
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
        self.config.wheels.rates(v, self.chassis.lateral_actuation)
    }
    fn sensor_payload(&self, a: Vector, wz: f64) -> Value {
        let names = self.config.wheels.names(self.chassis.lateral_actuation);
        let mut sample = json!({"joint_states":{"name":names,"position":self.wheel_positions,"velocity":self.wheel_rates,"effort":[]},"imu":{"angular_velocity_z_radps":wz,"linear_acceleration_x_mps2":a.x,"linear_acceleration_y_mps2":a.y}});
        if let Some(t) = &self.turret {
            sample["turret_joint_states"] = t.sample(&self.world, self.tank);
        }
        if let Some(c) = &self.cannon {
            sample["weapon_state"] = c.state(self.tick);
        }
        sample
    }
    pub fn set_turret_target(&mut self, target: TurretTarget) -> Result<(), String> {
        self.turret
            .as_mut()
            .ok_or("Weapons disabled")?
            .set_target(target, self.tick)
    }
    pub fn revoke_turret_target(&mut self) {
        if let Some(t) = &mut self.turret {
            t.revoke();
        }
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
    pub fn queue_fire(&mut self, request: ShotRequest) -> Result<(), String> {
        self.cannon
            .as_mut()
            .ok_or("Weapons disabled")?
            .queue(request, self.tick)
    }
    pub fn step(&mut self) -> Result<(), String> {
        if let (Some(c), Some(t)) = (&mut self.cannon, &self.turret) {
            let before = self.world.bodies[self.tank].linvel();
            c.begin_tick(
                &mut self.world,
                self.tank,
                t,
                &self.chassis,
                self.tick,
                self.config.clock.physics_hz,
            )?;
            let b = &self.world.bodies[self.tank];
            self.delta_v_body += b.rotation().inverse() * (b.linvel() - before);
        }
        let goal = self
            .target
            .filter(|t| {
                (self.tick - t.source_tick) as f64 / (self.config.clock.physics_hz as f64)
                    < self.timeout_s
            })
            .map(|t| [t.vx, t.vy, t.wz])
            .unwrap_or([0.0; 3]);
        let dt = self.world.integration_parameters.dt;
        for substep in 0..self.config.clock.substeps {
            let before = self.body_velocity();
            let rates = self.rates(before);
            let b = &mut self.world.bodies[self.tank];
            let old_pose = *b.position();
            let old_v = b.linvel();
            let old_angle = b.rotation().angle();
            drive_servo(
                &mut self.world,
                self.tank,
                &self.config,
                &self.chassis,
                goal,
            );
            let enemy_starts: BTreeMap<_, _> = self
                .enemies
                .iter()
                .map(|(id, enemy)| (id.clone(), *self.world.bodies[enemy.body].position()))
                .collect();
            for enemy in self.enemies.values_mut() {
                enemy.apply(&mut self.world, &self.config, self.tick);
            }
            if let Some(t) = &self.turret {
                t.apply_servo(
                    &mut self.world,
                    self.tank,
                    self.tick,
                    self.config.clock.physics_hz,
                );
            }
            self.world.step();
            if let Some(c) = &mut self.cannon {
                for (id, enemy) in &self.enemies {
                    let start = enemy_starts[id];
                    let end = *self.world.bodies[enemy.body].position();
                    c.dynamic_targets.insert(
                        id.clone(),
                        cannon::DynamicTarget {
                            body: enemy.body,
                            chassis: enemy.chassis.clone(),
                            motion: rapier2d_f64::parry::query::NonlinearRigidMotion::new(
                                start,
                                Vector::ZERO,
                                (end.translation - start.translation) / dt,
                                normalize_angle(end.rotation.angle() - start.rotation.angle()) / dt,
                            ),
                        },
                    );
                }
                let end = *self.world.bodies[self.tank].position();
                let start_s =
                    self.tick as f64 / self.config.clock.physics_hz as f64 + substep as f64 * dt;
                c.advance(
                    &mut self.world,
                    self.tank,
                    &self.chassis,
                    &self.config.body,
                    old_pose,
                    end,
                    start_s,
                    dt,
                )?;
                for obstacle in &mut c.obstacles {
                    if let Some(enemy) = obstacle
                        .target_id
                        .as_ref()
                        .and_then(|id| self.enemies.get(id))
                    {
                        obstacle.pose = *self.world.bodies[enemy.body].position();
                    }
                }
            }
            self.remove_dead_targets();
            if let Some(t) = &mut self.turret {
                t.observe_angle(&self.world, self.tank);
            }
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
        Ok(())
    }
    fn target_snapshot(&self, target: &TargetConfig) -> Value {
        if let Some(dead) = self.destroyed_targets.get(&target.target_id) {
            return dead.clone();
        }
        let hits = self
            .cannon
            .as_ref()
            .and_then(|c| c.target_hits.get(&target.target_id))
            .copied()
            .unwrap_or(0);
        let hp = target.health.as_ref().map(|h| {
            h.max_hp
                .saturating_sub(hits.saturating_mul(h.damage_per_hit))
        });
        let (pose, velocity) = if let Some(enemy) = self.enemies.get(&target.target_id) {
            let b = &self.world.bodies[enemy.body];
            let v = b.rotation().inverse() * b.linvel();
            (
                [
                    b.translation().x,
                    b.translation().y,
                    normalize_angle(b.rotation().angle()),
                ],
                [v.x, v.y, b.angvel()],
            )
        } else {
            (target.pose, [0.0; 3])
        };
        json!({"target_id":target.target_id,"pose":pose,"velocity":velocity,"hp":hp,"alive":hp != Some(0)})
    }
    fn remove_dead_targets(&mut self) {
        let dead: Vec<_> = self
            .config
            .weapons
            .targets
            .iter()
            .filter(|t| {
                t.health.is_some()
                    && self.target_snapshot(t)["alive"] == false
                    && !self.destroyed_targets.contains_key(&t.target_id)
            })
            .map(|t| (t.target_id.clone(), self.target_snapshot(t)))
            .collect();
        for (id, snapshot) in dead {
            if let Some(enemy) = self.enemies.remove(&id) {
                self.world.remove_body(enemy.turret.body);
                self.world.remove_body(enemy.body);
            }
            if let Some(c) = &mut self.cannon {
                c.dynamic_targets.remove(&id);
                c.obstacles.retain(|o| o.target_id.as_ref() != Some(&id));
            }
            self.destroyed_targets.insert(id, snapshot);
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
            weapon_state: self.cannon.as_ref().map(|c|c.state(self.tick)),
            projectiles: self.cannon.as_ref().map(|c|c.private_projectiles()).unwrap_or(json!([])),
            fire_results: self.cannon.as_ref().map(|c|json!(c.results)).unwrap_or(json!([])),
            weapon_events: self.cannon.as_ref().map(|c|json!(c.events)).unwrap_or(json!([])),
            target_hits: self.cannon.as_ref().map(|c|json!(c.target_hits)).unwrap_or(json!({})),
            targets: json!(self.config.weapons.targets.iter().map(|t| self.target_snapshot(t)).collect::<Vec<_>>()),
            turret_state: self.turret.as_ref().map(|t|json!({"relative_angle_rad":t.relative_angle,
                "relative_rate_radps":self.world.bodies[t.body].angvel()-b.angvel(),
                "position":[self.world.bodies[t.body].translation().x,self.world.bodies[t.body].translation().y],
                "world_yaw_rad":self.world.bodies[t.body].rotation().angle()})),
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
        c.step()?;
    }
    Ok(c.private_snapshot().truth_pose[0])
}
pub fn run_wheel_probe(text: &str) -> Result<Vec<f64>, String> {
    let raw: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let config: Config = serde_json::from_value(raw.clone()).map_err(|e| e.to_string())?;
    config.wheels.validate()?;
    let target: [f64; 3] = serde_json::from_value(raw["validation"]["probe_target"].clone())
        .map_err(|e| e.to_string())?;
    Ok(config.wheels.rates(target, true))
}
pub fn run_weapon_probe(text: &str) -> Result<Value, String> {
    let raw: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let config: Config = serde_json::from_value(raw.clone()).map_err(|e| e.to_string())?;
    let ticks = raw["validation"]["ticks"]
        .as_u64()
        .ok_or("Missing probe ticks")?;
    let period = raw["module"]["weapon_demo"]["fire_period_ticks"]
        .as_u64()
        .filter(|p| *p > 0)
        .ok_or("Invalid fire period")?;
    let rate = number(&raw["module"]["weapon_demo"], "turret_velocity_radps")?;
    let name = config.scene.default_chassis.clone();
    let mut c = GameCore::new(config, &name)?;
    for tick in 0..ticks {
        c.set_turret_target(TurretTarget {
            velocity_radps: rate,
            source_tick: tick,
        })?;
        if tick.is_multiple_of(period) {
            c.queue_fire(ShotRequest {
                publisher_id: "probe".into(),
                request_id: format!("probe-{tick}"),
                source_tick: tick,
            })?;
        }
        c.step()?;
    }
    let snapshot = c.private_snapshot();
    Ok(
        json!({"weapon_state":snapshot.weapon_state,"relative_angle_rad":snapshot.turret_state.unwrap()["relative_angle_rad"],"truth_pose":snapshot.truth_pose}),
    )
}
// Trusted build probe, not the browser deployment API. Single source of physical parameters.
#[cfg(target_arch = "wasm32")]
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_m1_probe() -> f64 {
    run_build_probe(include_str!("../../config/m1.json")).expect("Invalid profile")
}
#[cfg(target_arch = "wasm32")]
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_omni_wheel_probe() -> f64 {
    run_wheel_probe(include_str!("../../config/m1.json")).expect("Invalid wheel calibration")[0]
}
#[cfg(target_arch = "wasm32")]
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_m1b_probe() -> f64 {
    run_weapon_probe(include_str!("../../config/m1.json")).expect("Invalid weapon profile")["weapon_state"]["shots_fired"].as_f64().unwrap()
}
#[cfg(target_arch = "wasm32")]
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_m1b_angle_probe() -> f64 {
    run_weapon_probe(include_str!("../../config/m1.json")).expect("Invalid weapon profile")["relative_angle_rad"].as_f64().unwrap()
}
