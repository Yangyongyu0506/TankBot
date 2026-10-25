//! Shared private JSON DTO session for native IPC and browser WASM. Not a public protocol endpoint.
use crate::{Config, GameCore, TurretAccelerationTarget, TurretTarget, VelocityTarget};
use serde_json::{Value, json};

#[derive(Default)]
pub struct CoreSession {
    core: Option<GameCore>,
}
impl CoreSession {
    pub fn call(&mut self, r: Value) -> Result<Value, String> {
        match r["op"].as_str() {
            Some("init") => {
                let c: Config =
                    serde_json::from_value(r["config"].clone()).map_err(|e| e.to_string())?;
                self.core = Some(GameCore::new(
                    c,
                    r["chassis"].as_str().ok_or("Missing chassis")?,
                )?);
            }
            Some("step") => {
                let c = self.core.as_mut().ok_or("Not initialized")?;
                if r["revoke"] == true {
                    c.revoke_target();
                }
                if !r["target"].is_null() {
                    let t: VelocityTarget =
                        serde_json::from_value(r["target"].clone()).map_err(|e| e.to_string())?;
                    c.set_target(t)?;
                }
                if r["revoke_turret"] == true {
                    c.revoke_turret_target();
                }
                if !r["turret_target"].is_null() {
                    let target: TurretTarget = serde_json::from_value(r["turret_target"].clone())
                        .map_err(|e| e.to_string())?;
                    c.set_turret_target(target)?;
                }
                if !r["turret_acceleration_target"].is_null() {
                    let target: TurretAccelerationTarget =
                        serde_json::from_value(r["turret_acceleration_target"].clone())
                            .map_err(|e| e.to_string())?;
                    c.set_turret_acceleration(target)?;
                }
                if let Some(requests) = r["fire_requests"].as_array() {
                    for request in requests {
                        c.queue_fire(
                            serde_json::from_value(request.clone()).map_err(|e| e.to_string())?,
                        )?;
                    }
                }
                c.step()?;
            }
            Some("snapshot") => {}
            Some("probe") => {
                return Ok(json!(crate::run_build_probe(&r["config"].to_string())?));
            }
            Some("weapons_probe") => {
                return crate::run_weapon_probe(&r["config"].to_string());
            }
            Some("wheel_probe") => {
                return Ok(json!(crate::run_wheel_probe(&r["config"].to_string())?));
            }
            _ => return Err("Unknown operation".into()),
        }
        serde_json::to_value(
            self.core
                .as_ref()
                .ok_or("Not initialized")?
                .private_snapshot(),
        )
        .map_err(|e| e.to_string())
    }
    pub fn exchange(&mut self, raw: &[u8]) -> Vec<u8> {
        let result = serde_json::from_slice(raw)
            .map_err(|e| e.to_string())
            .and_then(|r| self.call(r));
        serde_json::to_vec(&match result {
            Ok(data) => json!({"ok":true,"data":data}),
            Err(error) => json!({"ok":false,"error":error}),
        })
        .expect("JSON response")
    }
}
