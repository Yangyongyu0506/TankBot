//! Trusted patrol controller using the same force servo and contact world as the player.
use crate::{Chassis, Config, TurretSystem, boolean, cannon::body_shape, normalize_angle, number};
use rapier2d_f64::prelude::*;
use serde::Deserialize;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PatrolConfig {
    pub chassis: String,
    pub initial_velocity: [f64; 3],
    pub initial_turret_angle_rad: f64,
    pub initial_turret_rate_radps: f64,
    pub control_hz: u64,
    pub waypoints_m: Vec<[f64; 2]>,
    pub forward_speed_mps: f64,
    pub heading_gain_per_s: f64,
    pub max_yaw_rate_radps: f64,
    pub turn_in_place_threshold_rad: f64,
    pub arrival_radius_m: f64,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HealthConfig {
    pub max_hp: u64,
    pub damage_per_hit: u64,
    pub collision_damage: u64,
    pub death_behavior: String,
}

pub(crate) fn drive_servo(
    world: &mut PhysicsWorld,
    body: RigidBodyHandle,
    config: &Config,
    chassis: &Chassis,
    goal: [f64; 3],
) {
    let b = &mut world.bodies[body];
    let v = b.rotation().inverse() * b.linvel();
    let wz = b.angvel();
    let s = &config.servo;
    let fx = (config.body.mass_kg * (goal[0] - v.x) / s.tau_x_s)
        .clamp(-s.max_force_x_n, s.max_force_x_n)
        - chassis.drag_x_n_s_per_m * v.x;
    let fy = (if chassis.lateral_actuation {
        (config.body.mass_kg * (goal[1] - v.y) / s.tau_y_s).clamp(-s.max_force_y_n, s.max_force_y_n)
    } else {
        0.0
    }) - chassis.drag_y_n_s_per_m * v.y;
    let mz = (config.body.yaw_inertia_kg_m2 * (goal[2] - wz) / s.tau_yaw_s)
        .clamp(-s.max_torque_nm, s.max_torque_nm)
        - chassis.drag_yaw_nm_s * wz;
    let force = *b.rotation() * Vector::new(fx, fy);
    b.reset_forces(true);
    b.reset_torques(true);
    b.add_force(force, true);
    b.add_torque(mz, true);
}

pub(crate) struct EnemyTank {
    pub body: RigidBodyHandle,
    pub turret: TurretSystem,
    pub chassis: Chassis,
    patrol: PatrolConfig,
    waypoint: usize,
    goal: [f64; 3],
    last_control_tick: Option<u64>,
}

impl EnemyTank {
    pub fn new(
        world: &mut PhysicsWorld,
        config: &Config,
        pose: [f64; 3],
        patrol: PatrolConfig,
    ) -> Result<Self, String> {
        if patrol.control_hz == 0
            || !config.clock.physics_hz.is_multiple_of(patrol.control_hz)
            || patrol.waypoints_m.is_empty()
            || patrol.waypoints_m.len() > 64
            || patrol.waypoints_m.iter().flatten().any(|v| !v.is_finite())
            || [
                patrol.forward_speed_mps,
                patrol.heading_gain_per_s,
                patrol.max_yaw_rate_radps,
                patrol.turn_in_place_threshold_rad,
                patrol.arrival_radius_m,
            ]
            .iter()
            .any(|v| !v.is_finite() || *v <= 0.0)
            || patrol.initial_velocity != [0.0; 3]
            || patrol.initial_turret_angle_rad != 0.0
            || patrol.initial_turret_rate_radps != 0.0
        {
            return Err("Invalid confirmed patrol profile".into());
        }
        let chassis = config
            .chassis
            .get(&patrol.chassis)
            .ok_or("Unknown enemy chassis")?
            .clone();
        let b = &config.body;
        let rb = RigidBodyBuilder::dynamic()
            .translation(Vector::new(pose[0], pose[1]))
            .rotation(pose[2])
            .linvel(
                Rotation::from_angle(pose[2])
                    * Vector::new(patrol.initial_velocity[0], patrol.initial_velocity[1]),
            )
            .angvel(patrol.initial_velocity[2])
            .can_sleep(boolean(&config.rigid_body, "can_sleep")?)
            .ccd_enabled(boolean(&config.rigid_body, "ccd_enabled")?)
            .linear_damping(number(&config.rigid_body, "linear_damping")?)
            .angular_damping(number(&config.rigid_body, "angular_damping")?);
        let collider = ColliderBuilder::new(body_shape(b))
            .mass_properties(MassProperties::new(
                Vector::ZERO,
                b.mass_kg,
                b.yaw_inertia_kg_m2,
            ))
            .friction(number(&config.contact, "friction")?)
            .restitution(number(&config.contact, "restitution")?);
        let (body, _) = world.insert(rb, collider);
        let mut turret_config = config.weapons.turret.clone();
        turret_config.initial_relative_angle_rad = patrol.initial_turret_angle_rad;
        turret_config.initial_relative_rate_radps = patrol.initial_turret_rate_radps;
        let turret = TurretSystem::new(world, body, turret_config, &config.rigid_body)?;
        Ok(Self {
            body,
            turret,
            chassis,
            patrol,
            waypoint: 0,
            goal: [0.0; 3],
            last_control_tick: None,
        })
    }

    pub fn apply(&mut self, world: &mut PhysicsWorld, config: &Config, tick: u64) {
        if tick.is_multiple_of(config.clock.physics_hz / self.patrol.control_hz)
            && self.last_control_tick != Some(tick)
        {
            self.last_control_tick = Some(tick);
            let body = &world.bodies[self.body];
            let p = body.translation();
            let mut point = self.patrol.waypoints_m[self.waypoint];
            if (Vector::new(point[0], point[1]) - p).length() <= self.patrol.arrival_radius_m {
                self.waypoint = (self.waypoint + 1) % self.patrol.waypoints_m.len();
                point = self.patrol.waypoints_m[self.waypoint];
            }
            let e =
                normalize_angle((point[1] - p.y).atan2(point[0] - p.x) - body.rotation().angle());
            let vx = if e.abs() > self.patrol.turn_in_place_threshold_rad {
                0.0
            } else {
                self.patrol.forward_speed_mps
            };
            self.goal = [
                vx.min(number(&config.motion_limits, "max_vx_mps").expect("Validated limits")),
                0.0,
                (self.patrol.heading_gain_per_s * e)
                    .clamp(
                        -self.patrol.max_yaw_rate_radps,
                        self.patrol.max_yaw_rate_radps,
                    )
                    .clamp(
                        -number(&config.motion_limits, "max_wz_radps").expect("Validated limits"),
                        number(&config.motion_limits, "max_wz_radps").expect("Validated limits"),
                    ),
            ];
        }
        drive_servo(world, self.body, config, &self.chassis, self.goal);
        self.turret
            .apply_servo(world, self.body, tick, config.clock.physics_hz);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{GameCore, ShotRequest, TargetConfig};
    use serde_json::Value;

    fn enemy_core() -> GameCore {
        let raw: Value =
            serde_json::from_str(include_str!("../tests/fixtures/default-profile.json")).unwrap();
        let mut config: Config = serde_json::from_value(raw.clone()).unwrap();
        let mut target: TargetConfig =
            serde_json::from_value(raw["campaign"]["levels"]["c2"]["target"].clone()).unwrap();
        target.pose = [2.0, 0.1, 0.0];
        target.motion.as_mut().unwrap().forward_speed_mps = 1e-9;
        target.motion.as_mut().unwrap().waypoints_m = vec![[4.0, 0.1]];
        config.scene.walls.clear();
        config.weapons.targets = vec![target];
        GameCore::new(config, "differential").unwrap()
    }

    #[test]
    fn hit_transfers_momentum_and_off_center_yaw_without_mass_gain() {
        let mut core = enemy_core();
        let id = "patrol_enemy";
        let body = core.enemies[id].body;
        let mass = core.world.bodies[body].mass();
        core.queue_fire(ShotRequest {
            publisher_id: "test".into(),
            request_id: "one".into(),
            source_tick: 0,
        })
        .unwrap();
        for _ in 0..100 {
            core.step().unwrap();
            if core.cannon.as_ref().unwrap().target_hits[id] > 0 {
                break;
            }
        }
        assert_eq!(core.cannon.as_ref().unwrap().target_hits[id], 1);
        let rb = &core.world.bodies[body];
        assert!(rb.linvel().x > 0.005);
        assert!(rb.angvel() > 0.001);
        assert_eq!(rb.mass(), mass);
        assert_eq!(core.private_snapshot().targets[0]["hp"], 2);
    }

    #[test]
    fn lethal_hit_removes_both_bodies_and_projectile_obstacle() {
        let mut core = enemy_core();
        let base = core.enemies["patrol_enemy"].body;
        let turret = core.enemies["patrol_enemy"].turret.body;
        for tick in 0..180 {
            if tick == 0 || tick == 20 || tick == 40 {
                core.queue_fire(ShotRequest {
                    publisher_id: "test".into(),
                    request_id: format!("shot-{tick}"),
                    source_tick: tick,
                })
                .unwrap();
            }
            core.step().unwrap();
        }
        assert_eq!(core.cannon.as_ref().unwrap().target_hits["patrol_enemy"], 3);
        assert!(core.world.bodies.get(base).is_none());
        assert!(core.world.bodies.get(turret).is_none());
        assert!(core.cannon.as_ref().unwrap().obstacles.is_empty());
        assert_eq!(core.private_snapshot().targets[0]["alive"], false);
        assert_eq!(core.private_snapshot().targets[0]["hp"], 0);
    }

    #[test]
    fn patrol_visits_all_waypoints_with_differential_enemy_and_omni_player() {
        let raw: Value =
            serde_json::from_str(include_str!("../tests/fixtures/default-profile.json")).unwrap();
        let mut config: Config = serde_json::from_value(raw.clone()).unwrap();
        let target: TargetConfig =
            serde_json::from_value(raw["campaign"]["levels"]["c2"]["target"].clone()).unwrap();
        let route = target.motion.as_ref().unwrap().waypoints_m.clone();
        let radius = target.motion.as_ref().unwrap().arrival_radius_m;
        config.weapons.targets = vec![target];
        let mut core = GameCore::new(config, "omnidirectional").unwrap();
        assert!(core.chassis.lateral_actuation);
        assert!(!core.enemies["patrol_enemy"].chassis.lateral_actuation);
        let mut visited = vec![false; route.len()];
        for _ in 0..4000 {
            core.step().unwrap();
            let p = core.world.bodies[core.enemies["patrol_enemy"].body].translation();
            for (i, waypoint) in route.iter().enumerate() {
                visited[i] |= (p - Vector::new(waypoint[0], waypoint[1])).length() <= radius;
            }
        }
        assert!(visited.iter().all(|hit| *hit), "{visited:?}");
    }
}
