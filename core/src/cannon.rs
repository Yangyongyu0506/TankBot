//! Deterministic, event-ordered circular projectiles. No renderer or player estimates.
use crate::{BodyConfig, Chassis, TurretSystem, normalize_angle};
use rapier2d_f64::{
    parry::query::{self, NonlinearRigidMotion, ShapeCastOptions},
    prelude::*,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectileConfig {
    pub mass_kg: f64,
    pub radius_m: f64,
    pub relative_speed_mps: f64,
    pub wall_restitution: f64,
    pub wall_friction: f64,
    pub max_bounces: u32,
    pub lifetime_s: f64,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FiringConfig {
    pub cooldown_s: f64,
    pub trigger: String,
    pub ammunition: String,
    pub request_cache_capacity: usize,
    pub pending_capacity: usize,
    pub max_active_projectiles: usize,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Numerics {
    pub time_epsilon_s: f64,
    pub spatial_epsilon_m: f64,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TargetConfig {
    pub target_id: String,
    pub pose: [f64; 3],
    pub motion: Option<crate::enemy::PatrolConfig>,
    pub health: Option<crate::enemy::HealthConfig>,
}
#[derive(Clone, Deserialize, Serialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct ShotRequest {
    pub publisher_id: String,
    pub request_id: String,
    pub source_tick: u64,
}
#[derive(Clone, Serialize, Debug)]
pub struct FireResult {
    pub request_id: String,
    pub status: String,
    pub processed_tick: u64,
}

#[derive(Clone)]
pub struct Projectile {
    pub id: u64,
    pub position: Vector,
    pub velocity: Vector,
    pub born_s: f64,
    pub bounces: u32,
    pub owner_armed: bool,
}
pub struct Obstacle {
    pub pose: Pose,
    pub shape: SharedShape,
    pub target_id: Option<String>,
}
pub struct DynamicTarget {
    pub body: RigidBodyHandle,
    pub chassis: Chassis,
    pub motion: NonlinearRigidMotion,
}
#[derive(Clone)]
enum EventKind {
    Expire,
    Exit,
    Hit {
        target: Option<String>,
        point: Vector,
    },
    Pair(usize),
    Wall {
        index: usize,
        normal: Vector,
    },
}
#[derive(Clone)]
struct Event {
    time: f64,
    shot: usize,
    kind: EventKind,
}

pub struct CannonSystem {
    pub projectile: ProjectileConfig,
    pub firing: FiringConfig,
    pub numerics: Numerics,
    pub obstacles: Vec<Obstacle>,
    pub dynamic_targets: BTreeMap<String, DynamicTarget>,
    pub shots: Vec<Projectile>,
    pub target_hits: BTreeMap<String, u64>,
    pub shots_fired: u64,
    pub hits_received: u64,
    pub results: Vec<(String, FireResult)>,
    pub events: Vec<Value>,
    pub last_result: Option<FireResult>,
    next_fire_tick: u64,
    next_id: u64,
    journal: BTreeMap<(String, String), FireResult>,
    pending: Vec<ShotRequest>,
}

pub fn body_shape(body: &BodyConfig) -> SharedShape {
    SharedShape::round_cuboid(
        body.length_m / 2.0 - body.corner_radius_m,
        body.width_m / 2.0 - body.corner_radius_m,
        body.corner_radius_m,
    )
}

/// Project at the actual impulse-time orientation; preserve its actual lever arm at the end gate.
pub fn apply_chassis_impulse(
    world: &mut PhysicsWorld,
    tank: RigidBodyHandle,
    chassis: &Chassis,
    impulse: Vector,
    point: Vector,
    reference: Pose,
) {
    let impulse = if chassis.lateral_actuation {
        impulse
    } else {
        let local = reference.rotation.inverse() * impulse;
        reference.rotation * Vector::new(local.x, 0.0)
    };
    let base = &mut world.bodies[tank];
    let application = base.translation() + (point - reference.translation);
    base.apply_impulse_at_point(impulse, application, true);
}

fn options(time: f64) -> ShapeCastOptions {
    ShapeCastOptions {
        max_time_of_impact: time,
        target_distance: 0.0,
        stop_at_penetration: false,
        compute_impact_geometry_on_penetration: true,
    }
}
fn intersects(p: Vector, r: f64, pose: &Pose, shape: &dyn Shape) -> bool {
    query::intersection_test(&Pose::translation(p.x, p.y), &Ball::new(r), pose, shape)
        .expect("Supported shapes")
        .intersecting
}
fn pair_time(a: &Projectile, b: &Projectile, r: f64, limit: f64) -> Option<f64> {
    let p = a.position - b.position;
    let v = a.velocity - b.velocity;
    let c = p.length_squared() - (2.0 * r).powi(2);
    if c <= 0.0 {
        return Some(0.0);
    }
    let vv = v.length_squared();
    if vv == 0.0 {
        return None;
    }
    let pv = p.dot(v);
    if pv >= 0.0 {
        return None;
    }
    let discriminant = pv * pv - vv * c;
    if discriminant < 0.0 {
        return None;
    }
    let t = c / (-pv + discriminant.sqrt()); // stable entry root
    (t >= 0.0 && t <= limit).then_some(t)
}

impl CannonSystem {
    pub fn new(
        config: &crate::WeaponsConfig,
        body: &BodyConfig,
        walls: &[crate::Wall],
    ) -> Result<Self, String> {
        let p = config.projectile.clone();
        let f = config.firing.clone();
        let n = config.numerics.clone();
        if [
            p.mass_kg,
            p.radius_m,
            p.relative_speed_mps,
            p.lifetime_s,
            f.cooldown_s,
            n.time_epsilon_s,
            n.spatial_epsilon_m,
        ]
        .iter()
        .any(|x| !x.is_finite() || *x <= 0.0)
            || p.wall_restitution != 1.0
            || p.wall_friction != 0.0
            || f.trigger != "single"
            || f.ammunition != "unlimited"
            || f.max_active_projectiles == 0
            || f.pending_capacity == 0
            || f.request_cache_capacity == 0
        {
            return Err("Invalid/unsupported cannon profile".into());
        }
        let expected_impact = json!({"momentum":"world_velocity","application_body":"chassis","application_point":"contact_or_muzzle","direction_rule":"chassis_capability","timing":"substep_end"});
        let expected_collision = json!({"owner_immunity":"until_exit","projectile_pair":"destroy_both","simultaneous_pairs":"destroy_contact_graph","priority":"target_pair_wall","wall_order":"stable_id","blocked_muzzle":"reject_without_recoil_or_cooldown"});
        if config.impact != expected_impact || config.collision != expected_collision {
            return Err("Unsupported weapon rules".into());
        }
        let mut obstacles: Vec<_> = walls
            .iter()
            .map(|w| Obstacle {
                pose: Pose::translation(w.center[0], w.center[1]),
                shape: SharedShape::cuboid(w.size[0] / 2.0, w.size[1] / 2.0),
                target_id: None,
            })
            .collect();
        let mut target_hits = BTreeMap::new();
        for t in &config.targets {
            if target_hits.insert(t.target_id.clone(), 0).is_some() {
                return Err("Duplicate target ID".into());
            }
            obstacles.push(Obstacle {
                pose: Pose::new(Vector::new(t.pose[0], t.pose[1]), t.pose[2]),
                shape: body_shape(body),
                target_id: Some(t.target_id.clone()),
            });
        }
        Ok(Self {
            projectile: p,
            firing: f,
            numerics: n,
            obstacles,
            dynamic_targets: BTreeMap::new(),
            shots: vec![],
            target_hits,
            shots_fired: 0,
            hits_received: 0,
            results: vec![],
            events: vec![],
            last_result: None,
            next_fire_tick: 0,
            next_id: 0,
            journal: BTreeMap::new(),
            pending: vec![],
        })
    }
    pub fn queue(&mut self, request: ShotRequest, tick: u64) -> Result<(), String> {
        if request.source_tick > tick || request.request_id.is_empty() {
            return Err("Invalid fire request".into());
        }
        if self.pending.len() >= self.firing.pending_capacity {
            return Err("Fire queue full".into());
        }
        self.pending.push(request);
        Ok(())
    }
    pub fn begin_tick(
        &mut self,
        world: &mut PhysicsWorld,
        tank: RigidBodyHandle,
        turret: &TurretSystem,
        chassis: &Chassis,
        tick: u64,
        hz: u64,
    ) -> Result<(), String> {
        self.events.clear();
        self.results.clear();
        let cooldown = self.firing.cooldown_s * (hz as f64);
        if cooldown.fract() != 0.0 {
            return Err("Cooldown must be an integer tick count".into());
        }
        for request in std::mem::take(&mut self.pending) {
            let key = (request.publisher_id.clone(), request.request_id.clone());
            if let Some(old) = self.journal.get(&key) {
                self.results.push((request.publisher_id, old.clone()));
                continue;
            }
            let status = if self.journal.len() >= self.firing.request_cache_capacity {
                "resource_limit"
            } else if tick < self.next_fire_tick {
                "cooldown"
            } else if self.shots.len() >= self.firing.max_active_projectiles {
                "resource_limit"
            } else {
                let (muzzle, velocity, direction) = turret.muzzle(world);
                let pivot = world.bodies[turret.body].translation();
                let path = muzzle - pivot;
                let blocked = self.obstacles.iter().any(|o| {
                    query::cast_shapes(
                        &Pose::translation(pivot.x, pivot.y),
                        path,
                        &Ball::new(self.projectile.radius_m),
                        &o.pose,
                        Vector::ZERO,
                        o.shape.as_ref(),
                        ShapeCastOptions {
                            stop_at_penetration: true,
                            ..options(1.0)
                        },
                    )
                    .expect("Supported shapes")
                    .is_some()
                });
                if blocked {
                    "blocked"
                } else {
                    let owner_armed = !intersects(
                        muzzle,
                        self.projectile.radius_m,
                        world.bodies[tank].position(),
                        body_shape_from_world(world, tank),
                    );
                    self.shots.push(Projectile {
                        id: self.next_id,
                        position: muzzle,
                        velocity: velocity + direction * self.projectile.relative_speed_mps,
                        born_s: tick as f64 / hz as f64,
                        bounces: 0,
                        owner_armed,
                    });
                    self.next_id += 1;
                    self.shots_fired += 1;
                    let reference = *world.bodies[tank].position();
                    apply_chassis_impulse(
                        world,
                        tank,
                        chassis,
                        -direction * self.projectile.mass_kg * self.projectile.relative_speed_mps,
                        muzzle,
                        reference,
                    );
                    self.next_fire_tick = tick + cooldown as u64;
                    self.events.push(json!({"kind":"fired","projectile_id":self.next_id-1,"time_s":tick as f64/hz as f64}));
                    "fired"
                }
            };
            let result = FireResult {
                request_id: request.request_id,
                status: status.into(),
                processed_tick: tick,
            };
            if self.journal.len() < self.firing.request_cache_capacity {
                self.journal.insert(key, result.clone());
            }
            self.last_result = Some(result.clone());
            self.results.push((request.publisher_id, result));
        }
        Ok(())
    }

    /// Rigid motion is interpolated over the already integrated fixed substep. Hits write impulses at its end.
    pub fn advance(
        &mut self,
        world: &mut PhysicsWorld,
        tank: RigidBodyHandle,
        chassis: &Chassis,
        body: &BodyConfig,
        start: Pose,
        end: Pose,
        start_s: f64,
        dt: f64,
    ) -> Result<(), String> {
        let radius = self.projectile.radius_m;
        let ball = Ball::new(radius);
        let tank_shape = body_shape(body);
        let motion = NonlinearRigidMotion::new(
            start,
            Vector::ZERO,
            (end.translation - start.translation) / dt,
            normalize_angle(end.rotation.angle() - start.rotation.angle()) / dt,
        );
        let mut elapsed = 0.0;
        let mut alive = vec![true; self.shots.len()];
        let mut impulses = vec![];
        let mut target_impulses = vec![];
        let limit = self.firing.max_active_projectiles * (self.projectile.max_bounces as usize + 4);
        let mut rounds = 0;
        while elapsed < dt && alive.iter().any(|a| *a) {
            rounds += 1;
            if rounds > limit {
                return Err("PROJECTILE_SOLVER_DID_NOT_ADVANCE".into());
            }
            let remaining = dt - elapsed;
            let mut events = vec![];
            let base_pose = motion.position_at_time(elapsed);
            for (i, p) in self.shots.iter().enumerate().filter(|(i, _)| alive[*i]) {
                let ttl = p.born_s + self.projectile.lifetime_s - start_s - elapsed;
                if ttl <= remaining {
                    events.push(Event {
                        time: ttl.max(0.0),
                        shot: i,
                        kind: EventKind::Expire,
                    });
                }
                let pos = Pose::translation(p.position.x, p.position.y);
                for (j, o) in self.obstacles.iter().enumerate() {
                    if let Some(dynamic) = o
                        .target_id
                        .as_ref()
                        .and_then(|id| self.dynamic_targets.get(id))
                    {
                        let moving = NonlinearRigidMotion::new(
                            dynamic.motion.position_at_time(elapsed),
                            Vector::ZERO,
                            dynamic.motion.linvel,
                            dynamic.motion.angvel,
                        );
                        let shot = NonlinearRigidMotion::new(pos, Vector::ZERO, p.velocity, 0.0);
                        if let Some(hit) = query::cast_shapes_nonlinear(
                            &shot,
                            &ball,
                            &moving,
                            o.shape.as_ref(),
                            0.0,
                            remaining,
                            false,
                        )
                        .map_err(|e| format!("{e:?}"))?
                        {
                            events.push(Event {
                                time: hit.time_of_impact,
                                shot: i,
                                kind: EventKind::Hit {
                                    target: o.target_id.clone(),
                                    point: moving.position_at_time(hit.time_of_impact)
                                        * hit.witness2,
                                },
                            });
                        }
                        continue;
                    }
                    if let Some(hit) = query::cast_shapes(
                        &pos,
                        p.velocity,
                        &ball,
                        &o.pose,
                        Vector::ZERO,
                        o.shape.as_ref(),
                        options(remaining),
                    )
                    .map_err(|e| format!("{e:?}"))?
                    {
                        let kind = if let Some(id) = &o.target_id {
                            EventKind::Hit {
                                target: Some(id.clone()),
                                point: o.pose * hit.witness2,
                            }
                        } else {
                            EventKind::Wall {
                                index: j,
                                normal: o.pose.rotation * hit.normal2,
                            }
                        };
                        events.push(Event {
                            time: hit.time_of_impact,
                            shot: i,
                            kind,
                        });
                    }
                }
                let shot_motion = NonlinearRigidMotion::new(pos, Vector::ZERO, p.velocity, 0.0);
                let base_motion = NonlinearRigidMotion::new(
                    base_pose,
                    Vector::ZERO,
                    motion.linvel,
                    motion.angvel,
                );
                if p.owner_armed {
                    if let Some(hit) = query::cast_shapes_nonlinear(
                        &shot_motion,
                        &ball,
                        &base_motion,
                        tank_shape.as_ref(),
                        0.0,
                        remaining,
                        false,
                    )
                    .map_err(|e| format!("{e:?}"))?
                    {
                        events.push(Event {
                            time: hit.time_of_impact,
                            shot: i,
                            kind: EventKind::Hit {
                                target: None,
                                point: base_motion.position_at_time(hit.time_of_impact)
                                    * hit.witness2,
                            },
                        });
                    }
                } else {
                    let future = p.position + p.velocity * remaining;
                    let future_base = motion.position_at_time(dt);
                    if !intersects(p.position, radius, &base_pose, tank_shape.as_ref()) {
                        events.push(Event {
                            time: 0.0,
                            shot: i,
                            kind: EventKind::Exit,
                        });
                    } else if !intersects(future, radius, &future_base, tank_shape.as_ref()) {
                        let reverse_shot = NonlinearRigidMotion::new(
                            Pose::translation(future.x, future.y),
                            Vector::ZERO,
                            -p.velocity,
                            0.0,
                        );
                        let reverse_base = NonlinearRigidMotion::new(
                            future_base,
                            Vector::ZERO,
                            -motion.linvel,
                            -motion.angvel,
                        );
                        if let Some(hit) = query::cast_shapes_nonlinear(
                            &reverse_shot,
                            &ball,
                            &reverse_base,
                            tank_shape.as_ref(),
                            0.0,
                            remaining,
                            true,
                        )
                        .map_err(|e| format!("{e:?}"))?
                        {
                            events.push(Event {
                                time: (remaining - hit.time_of_impact).max(0.0),
                                shot: i,
                                kind: EventKind::Exit,
                            });
                        }
                    }
                }
                for j in i + 1..self.shots.len() {
                    if alive[j] {
                        if let Some(time) = pair_time(p, &self.shots[j], radius, remaining) {
                            events.push(Event {
                                time,
                                shot: i,
                                kind: EventKind::Pair(j),
                            });
                        }
                    }
                }
            }
            let Some(first) = events.iter().map(|e| e.time).min_by(f64::total_cmp) else {
                for (i, p) in self.shots.iter_mut().enumerate() {
                    if alive[i] {
                        p.position += p.velocity * remaining;
                    }
                }
                break;
            };
            for (i, p) in self.shots.iter_mut().enumerate() {
                if alive[i] {
                    p.position += p.velocity * first;
                }
            }
            elapsed += first;
            events.retain(|e| e.time <= first + self.numerics.time_epsilon_s);
            // Half-open lifetime wins ties, then owner exit (enables later collisions).
            for e in &events {
                match e.kind {
                    EventKind::Expire => alive[e.shot] = false,
                    EventKind::Exit => self.shots[e.shot].owner_armed = true,
                    _ => {}
                }
            }
            events.sort_by_key(|e| {
                (
                    e.shot,
                    match &e.kind {
                        EventKind::Hit { target, .. } => target.clone().unwrap_or_default(),
                        _ => String::new(),
                    },
                )
            });
            for e in &events {
                if !alive[e.shot] {
                    continue;
                }
                if let EventKind::Hit { target, point } = &e.kind {
                    alive[e.shot] = false;
                    let p = &self.shots[e.shot];
                    if let Some(id) = target {
                        *self.target_hits.get_mut(id).expect("Registered target") += 1;
                        if let Some(dynamic) = self.dynamic_targets.get(id) {
                            target_impulses.push((
                                dynamic.body,
                                dynamic.chassis.clone(),
                                p.velocity * self.projectile.mass_kg,
                                *point,
                                dynamic.motion.position_at_time(elapsed),
                            ));
                        }
                    } else {
                        self.hits_received += 1;
                        impulses.push((
                            p.velocity * self.projectile.mass_kg,
                            *point,
                            motion.position_at_time(elapsed),
                        ));
                    }
                    self.events.push(json!({"kind":"hit","projectile_id":p.id,"target_id":target,"time_s":start_s+elapsed}));
                }
            }
            let mut destroyed = BTreeSet::new();
            for e in &events {
                if let EventKind::Pair(j) = e.kind {
                    if alive[e.shot] && alive[j] {
                        destroyed.insert(e.shot);
                        destroyed.insert(j);
                    }
                }
            }
            for i in destroyed {
                alive[i] = false;
                self.events.push(json!({"kind":"projectile_collision","projectile_id":self.shots[i].id,"time_s":start_s+elapsed}));
            }
            events.sort_by_key(|e| match e.kind {
                EventKind::Wall { index, .. } => (e.shot, index),
                _ => (usize::MAX, usize::MAX),
            });
            for e in events {
                if !alive[e.shot] {
                    continue;
                }
                if let EventKind::Wall { index, normal } = e.kind {
                    let p = &mut self.shots[e.shot];
                    if p.bounces >= self.projectile.max_bounces {
                        alive[e.shot] = false;
                        continue;
                    }
                    p.velocity -= normal
                        * ((1.0 + self.projectile.wall_restitution) * p.velocity.dot(normal));
                    p.position += normal * self.numerics.spatial_epsilon_m;
                    p.bounces += 1;
                    self.events.push(json!({"kind":"bounce","projectile_id":p.id,"wall_index":index,"time_s":start_s+elapsed}));
                }
            }
        }
        let mut i = 0;
        self.shots.retain(|_| {
            let keep = alive[i];
            i += 1;
            keep
        });
        for (impulse, point, reference) in impulses {
            apply_chassis_impulse(world, tank, chassis, impulse, point, reference);
        }
        for (body, drive, impulse, point, reference) in target_impulses {
            apply_chassis_impulse(world, body, &drive, impulse, point, reference);
        }
        Ok(())
    }
    pub fn state(&self, tick: u64) -> Value {
        json!({"ready":tick>=self.next_fire_tick,"cooldown_remaining_ticks":self.next_fire_tick.saturating_sub(tick),
            "shots_fired":self.shots_fired,"hits_received":self.hits_received,"last_result":self.last_result})
    }
    pub fn private_projectiles(&self) -> Value {
        json!(self.shots.iter().map(|p|json!({"projectile_id":p.id,"position":[p.position.x,p.position.y],
            "velocity":[p.velocity.x,p.velocity.y],"bounces":p.bounces,"owner_armed":p.owner_armed,"born_s":p.born_s})).collect::<Vec<_>>())
    }
}

fn body_shape_from_world(world: &PhysicsWorld, tank: RigidBodyHandle) -> &dyn Shape {
    world.colliders[*world.bodies[tank]
        .colliders()
        .first()
        .expect("Tank collider")]
    .shape()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Config, GameCore};
    fn core(chassis: &str) -> GameCore {
        let mut c: Config = serde_json::from_str(include_str!("../../config/m1.json")).unwrap();
        c.scene.walls.clear();
        c.weapons.targets.clear();
        GameCore::new(c, chassis).unwrap()
    }
    fn shot(id: u64, position: Vector, velocity: Vector) -> Projectile {
        Projectile {
            id,
            position,
            velocity,
            born_s: 0.0,
            bounces: 0,
            owner_armed: true,
        }
    }
    fn advance(c: &mut GameCore, dt: f64) {
        let p = *c.world.bodies[c.tank].position();
        c.cannon
            .as_mut()
            .unwrap()
            .advance(
                &mut c.world,
                c.tank,
                &c.chassis,
                &c.config.body,
                p,
                p,
                0.0,
                dt,
            )
            .unwrap();
    }
    #[test]
    fn crossing_projectiles_and_simultaneous_graph_destroy_all() {
        for count in [2, 3] {
            let mut c = core("omnidirectional");
            let radius = c.config.weapons.projectile.radius_m;
            // Three tangent circles, all approaching the same contact time.
            let center = Vector::new(0.0, 2.0);
            c.cannon.as_mut().unwrap().shots = (0..count)
                .map(|id| {
                    let a = id as f64 * std::f64::consts::TAU / 3.0;
                    let n = Vector::new(a.cos(), a.sin());
                    shot(id, center + n * (2.0 * radius / 3.0_f64.sqrt() + 1.0), -n)
                })
                .collect();
            advance(&mut c, 1.1);
            assert!(c.cannon.as_ref().unwrap().shots.is_empty());
            assert_eq!(c.cannon.as_ref().unwrap().events.len(), count as usize);
        }
    }
    #[test]
    fn moving_pair_sweep_catches_tunneling_and_tangent() {
        let a = shot(0, Vector::new(-1.0, 2.0), Vector::new(1000.0, 0.0));
        let b = shot(1, Vector::new(1.0, 2.0), Vector::new(-1000.0, 0.0));
        assert!((pair_time(&a, &b, 0.03, 0.004).unwrap() - 0.00097).abs() < 1e-12);
        let b = shot(1, Vector::new(0.0, 2.06), Vector::ZERO);
        assert!((pair_time(&a, &b, 0.03, 0.004).unwrap() - 0.001).abs() < 1e-10);
    }
    #[test]
    fn wall_sweep_counts_each_wall_and_fourth_destroys() {
        let mut c = core("differential");
        let cannon = c.cannon.as_mut().unwrap();
        for x in [-1.0, 1.0] {
            cannon.obstacles.push(Obstacle {
                pose: Pose::translation(x, 2.0),
                shape: SharedShape::cuboid(0.01, 1.0),
                target_id: None,
            });
        }
        cannon
            .shots
            .push(shot(0, Vector::new(0.0, 2.0), Vector::new(1000.0, 0.0)));
        advance(&mut c, 0.01);
        let cannon = c.cannon.as_ref().unwrap();
        assert!(cannon.shots.is_empty());
        assert_eq!(
            cannon
                .events
                .iter()
                .filter(|e| e["kind"] == "bounce")
                .count(),
            3
        );
    }
    #[test]
    fn corner_counts_two_walls_in_stable_order() {
        let mut c = core("differential");
        let cannon = c.cannon.as_mut().unwrap();
        cannon.obstacles.push(Obstacle {
            pose: Pose::translation(1.0, 2.0),
            shape: SharedShape::cuboid(0.1, 2.0),
            target_id: None,
        });
        cannon.obstacles.push(Obstacle {
            pose: Pose::translation(0.0, 3.0),
            shape: SharedShape::cuboid(2.0, 0.1),
            target_id: None,
        });
        cannon
            .shots
            .push(shot(0, Vector::new(0.0, 2.0), Vector::new(1.0, 1.0)));
        advance(&mut c, 1.0);
        let cannon = c.cannon.as_ref().unwrap();
        assert_eq!(cannon.shots[0].bounces, 2);
        assert!(cannon.shots[0].velocity.x < 0.0 && cannon.shots[0].velocity.y < 0.0);
        assert_eq!(cannon.events[0]["wall_index"], 0);
        assert_eq!(cannon.events[1]["wall_index"], 1);
    }
    #[test]
    fn expiry_wins_exact_collision_and_no_early_expiry() {
        let mut c = core("differential");
        let life = c.config.weapons.projectile.lifetime_s;
        let r = c.config.weapons.projectile.radius_m;
        let cannon = c.cannon.as_mut().unwrap();
        cannon.obstacles.push(Obstacle {
            pose: Pose::translation(life + r + 0.01, 2.0),
            shape: SharedShape::cuboid(0.01, 1.0),
            target_id: None,
        });
        cannon
            .shots
            .push(shot(0, Vector::new(0.0, 2.0), Vector::new(1.0, 0.0)));
        advance(&mut c, life - 0.01);
        assert_eq!(c.cannon.as_ref().unwrap().shots.len(), 1);
        let p = *c.world.bodies[c.tank].position();
        c.cannon
            .as_mut()
            .unwrap()
            .advance(
                &mut c.world,
                c.tank,
                &c.chassis,
                &c.config.body,
                p,
                p,
                life - 0.01,
                0.01,
            )
            .unwrap();
        assert!(c.cannon.as_ref().unwrap().shots.is_empty());
        assert!(c.cannon.as_ref().unwrap().events.is_empty());
    }
    #[test]
    fn hit_world_momentum_projection_and_eccentric_torque_without_mass_gain() {
        for name in ["differential", "omnidirectional"] {
            let mut c = core(name);
            let mass = c.world.bodies[c.tank].mass();
            let radius = c.config.weapons.projectile.radius_m;
            let velocity = Vector::new(-2.0, -1.0);
            let momentum = velocity * c.config.weapons.projectile.mass_kg;
            // Side impact with a nonzero longitudinal component, at x=0.2.
            c.cannon.as_mut().unwrap().shots.push(shot(
                0,
                Vector::new(0.4, 0.4 + radius),
                velocity,
            ));
            advance(&mut c, 0.2);
            let b = &c.world.bodies[c.tank];
            assert_eq!(c.cannon.as_ref().unwrap().hits_received, 1);
            assert!(c.cannon.as_ref().unwrap().shots.is_empty());
            assert_eq!(b.mass(), mass);
            assert!((b.linvel().x - momentum.x / mass).abs() < 1e-12);
            if name == "differential" {
                assert_eq!(b.linvel().y, 0.0);
            } else {
                assert!((b.linvel().y - momentum.y / mass).abs() < 1e-12);
            }
            let expected_angular_impulse = if name == "differential" { 0.03 } else { 0.02 };
            assert!(
                (b.angvel() - expected_angular_impulse / c.config.body.yaw_inertia_kg_m2).abs()
                    < 1e-8
            );
        }
    }
    #[test]
    fn target_hit_precedes_pair_at_same_time() {
        let mut c = core("differential");
        let r = c.config.weapons.projectile.radius_m;
        let cannon = c.cannon.as_mut().unwrap();
        cannon.target_hits.insert("test".into(), 0);
        cannon.obstacles.push(Obstacle {
            pose: Pose::translation(1.1, 2.0),
            shape: SharedShape::cuboid(0.1, 0.1),
            target_id: Some("test".into()),
        });
        cannon
            .shots
            .push(shot(0, Vector::new(0.0, 2.0), Vector::new(1.0, 0.0)));
        cannon
            .shots
            .push(shot(1, Vector::new(1.0 - r, 2.0 + 2.0 * r), Vector::ZERO));
        advance(&mut c, 1.0);
        let cannon = c.cannon.as_ref().unwrap();
        assert_eq!(cannon.target_hits["test"], 1);
        assert_eq!(cannon.shots.len(), 1);
        assert_eq!(cannon.shots[0].id, 1);
    }
    #[test]
    fn owner_exit_then_wall_return_can_hit_in_same_substep() {
        let mut c = core("omnidirectional");
        let cannon = c.cannon.as_mut().unwrap();
        cannon.obstacles.push(Obstacle {
            pose: Pose::translation(0.6, 0.0),
            shape: SharedShape::cuboid(0.01, 1.0),
            target_id: None,
        });
        let mut p = shot(0, Vector::new(0.4, 0.0), Vector::new(15.0, 0.0));
        p.owner_armed = false;
        cannon.shots.push(p);
        advance(&mut c, 0.04);
        let cannon = c.cannon.as_ref().unwrap();
        assert_eq!(cannon.hits_received, 1);
        assert!(cannon.shots.is_empty());
    }
    #[test]
    fn rotating_body_sweep_catches_stationary_projectile() {
        let mut c = core("omnidirectional");
        c.cannon
            .as_mut()
            .unwrap()
            .shots
            .push(shot(0, Vector::new(0.0, 0.38), Vector::ZERO));
        let start = Pose::IDENTITY;
        let end = Pose::new(Vector::ZERO, std::f64::consts::FRAC_PI_2);
        c.cannon
            .as_mut()
            .unwrap()
            .advance(
                &mut c.world,
                c.tank,
                &c.chassis,
                &c.config.body,
                start,
                end,
                0.0,
                0.1,
            )
            .unwrap();
        assert_eq!(c.cannon.as_ref().unwrap().hits_received, 1);
        assert!(c.cannon.as_ref().unwrap().shots.is_empty());
    }
    #[test]
    fn pre_recoil_muzzle_velocity_and_axis_projection() {
        for name in ["differential", "omnidirectional"] {
            let mut c = core(name);
            c.world.bodies[c.tank].set_linvel(Vector::new(1.0, 0.0), true);
            let t = c.turret.as_ref().unwrap();
            c.world.bodies[t.body].set_linvel(Vector::new(1.0, 0.0), true);
            c.world.bodies[t.body].set_angvel(2.0, true);
            // Shoot across body x so differential must drop lateral recoil.
            c.world.bodies[t.body]
                .set_rotation(Rotation::from_angle(std::f64::consts::FRAC_PI_2), true);
            let (_, inherited, direction) = t.muzzle(&c.world);
            let mass = c.world.bodies[c.tank].mass();
            let cannon = c.cannon.as_mut().unwrap();
            cannon
                .queue(
                    ShotRequest {
                        publisher_id: "test".into(),
                        request_id: "one".into(),
                        source_tick: 0,
                    },
                    0,
                )
                .unwrap();
            cannon
                .begin_tick(
                    &mut c.world,
                    c.tank,
                    t,
                    &c.chassis,
                    0,
                    c.config.clock.physics_hz,
                )
                .unwrap();
            let p = &cannon.shots[0];
            assert!(
                (p.velocity - (inherited + direction * cannon.projectile.relative_speed_mps))
                    .length()
                    < 1e-12
            );
            let base = &c.world.bodies[c.tank];
            if name == "differential" {
                assert!(base.linvel().y.abs() < 1e-12);
            } else {
                assert!(
                    (base.linvel().y
                        + cannon.projectile.mass_kg * cannon.projectile.relative_speed_mps / mass)
                        .abs()
                        < 1e-12
                );
            }
        }
    }
}
