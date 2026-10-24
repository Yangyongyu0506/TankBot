use super::*;

fn core(name: &str, health: bool) -> GameCore {
    let raw: Value =
        serde_json::from_str(include_str!("../tests/fixtures/default-profile.json")).unwrap();
    let mut config: Config = serde_json::from_value(raw.clone()).unwrap();
    config.scene.walls.clear();
    config.weapons.targets.clear();
    if health {
        config.scene.player_health = Some(
            serde_json::from_value(raw["campaign"]["levels"]["c2"]["target"]["health"].clone())
                .unwrap(),
        );
    }
    GameCore::new(config, name).unwrap()
}

fn incoming(c: &mut GameCore, id: u64) {
    let base = &c.world.bodies[c.tank];
    let position = base.position() * Vector::new(0.49, 0.08);
    let velocity = *base.rotation() * Vector::new(-30.0, 0.0);
    c.cannon.as_mut().unwrap().shots.push(cannon::Projectile {
        id,
        position,
        velocity,
        born_s: c.tick as f64 / c.config.clock.physics_hz as f64,
        bounces: 1,
        owner_armed: true,
    });
}

#[test]
fn player_damage_removes_bodies_and_continues_without_a_ghost_collider() {
    for name in ["differential", "omnidirectional"] {
        let mut c = core(name, true);
        let body = c.tank;
        let turret = c.turret.as_ref().unwrap().body;
        let mass = c.world.bodies[body].mass();
        for id in 0..3 {
            incoming(&mut c, id);
            c.step().unwrap();
            assert_eq!(c.private_snapshot().player_hp, Some(2 - id));
            if id < 2 {
                assert_eq!(c.world.bodies[body].mass(), mass);
                assert!(c.world.bodies[body].linvel().x < 0.0);
            }
        }
        assert!(!c.private_snapshot().player_alive);
        assert!(c.world.bodies.get(body).is_none());
        assert!(c.world.bodies.get(turret).is_none());
        assert!(c.private_snapshot().turret_state.is_none());
        assert_eq!(c.private_snapshot().weapon_state.unwrap()["ready"], false);
        assert!(
            c.set_target(VelocityTarget {
                vx: 1.0,
                vy: 0.0,
                wz: 0.0,
                source_tick: c.tick
            })
            .is_err()
        );
        assert!(
            c.queue_fire(ShotRequest {
                publisher_id: "test".into(),
                request_id: "dead".into(),
                source_tick: c.tick
            })
            .is_err()
        );
        // A new test projectile passes through the removed player, rather than hitting a ghost body.
        c.cannon.as_mut().unwrap().shots.push(cannon::Projectile {
            id: 10,
            position: Vector::new(1.0, 0.0),
            velocity: Vector::new(-10.0, 0.0),
            born_s: c.tick as f64 / c.config.clock.physics_hz as f64,
            bounces: 0,
            owner_armed: true,
        });
        for _ in 0..12 {
            c.step().unwrap();
        }
        assert_eq!(c.cannon.as_ref().unwrap().hits_received, 3);
        assert!(c.cannon.as_ref().unwrap().shots[0].position.x < 0.0);
    }
}

#[test]
fn unconfigured_player_health_retains_hit_count_only() {
    let mut c = core("differential", false);
    for id in 0..4 {
        incoming(&mut c, id);
        c.step().unwrap();
    }
    assert!(c.private_snapshot().player_alive);
    assert_eq!(c.private_snapshot().player_hp, None);
    assert_eq!(c.cannon.as_ref().unwrap().hits_received, 4);
}
