//! Inspect the locked engine's settings when reviewing a new simulation profile.
fn main() {
    println!(
        "{}",
        serde_json::to_string_pretty(&rapier2d_f64::prelude::IntegrationParameters::default())
            .unwrap()
    );
}
