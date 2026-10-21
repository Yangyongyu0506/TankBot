//! Private stdio adapter, never connected to the player worker or browser.
use serde_json::{Value, json};
use std::io::{self, Read, Write};
use tankbot_core::{Config, GameCore, TurretTarget, VelocityTarget};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    let mut core: Option<GameCore> = None;
    loop {
        let mut length = [0u8; 4];
        match input.read_exact(&mut length) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(()),
            Err(e) => return Err(e.into()),
        };
        // Private bootstrap frame limit, not a physical parameter.
        let size = u32::from_be_bytes(length) as usize;
        if size > 1024 * 1024 {
            return Err("Private IPC frame too large".into());
        }
        let mut bytes = vec![0; size];
        input.read_exact(&mut bytes)?;
        let result = (|| -> Result<Value, String> {
            let r: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
            match r["op"].as_str() {
                Some("init") => {
                    let c: Config =
                        serde_json::from_value(r["config"].clone()).map_err(|e| e.to_string())?;
                    core = Some(GameCore::new(
                        c,
                        r["chassis"].as_str().ok_or("Missing chassis")?,
                    )?);
                }
                Some("step") => {
                    let c = core.as_mut().ok_or("Not initialized")?;
                    if r["revoke"] == true {
                        c.revoke_target();
                    }
                    if !r["target"].is_null() {
                        let t: VelocityTarget = serde_json::from_value(r["target"].clone())
                            .map_err(|e| e.to_string())?;
                        c.set_target(t)?;
                    }
                    if r["revoke_turret"] == true {
                        c.revoke_turret_target();
                    }
                    if !r["turret_target"].is_null() {
                        let target: TurretTarget =
                            serde_json::from_value(r["turret_target"].clone())
                                .map_err(|e| e.to_string())?;
                        c.set_turret_target(target)?;
                    }
                    if let Some(requests) = r["fire_requests"].as_array() {
                        for request in requests {
                            c.queue_fire(
                                serde_json::from_value(request.clone())
                                    .map_err(|e| e.to_string())?,
                            )?;
                        }
                    }
                    c.step()?;
                }
                Some("snapshot") => {}
                Some("probe") => {
                    return Ok(json!(tankbot_core::run_build_probe(
                        &r["config"].to_string()
                    )?));
                }
                Some("weapons_probe") => {
                    return tankbot_core::run_weapon_probe(&r["config"].to_string());
                }
                _ => return Err("Unknown operation".into()),
            }
            serde_json::to_value(core.as_ref().ok_or("Not initialized")?.private_snapshot())
                .map_err(|e| e.to_string())
        })();
        let r = match result {
            Ok(v) => json!({"ok":true,"data":v}),
            Err(e) => json!({"ok":false,"error":e}),
        };
        let raw = serde_json::to_vec(&r)?;
        output.write_all(&(raw.len() as u32).to_be_bytes())?;
        output.write_all(&raw)?;
        output.flush()?;
    }
}
