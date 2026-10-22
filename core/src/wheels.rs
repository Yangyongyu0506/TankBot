//! Ideal rolling observations. Wheel geometry is calibration, never a second physics engine.
use serde::Deserialize;
use std::{collections::BTreeSet, f64::consts::TAU};

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WheelMount {
    pub name: String,
    pub azimuth_deg: f64,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RadialOmni {
    pub geometry_version: String,
    pub center_radius_m: f64,
    pub wheels: Vec<WheelMount>,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Wheels {
    pub radius_m: f64,
    pub differential_track_m: f64,
    pub omnidirectional: RadialOmni,
}
impl Wheels {
    pub fn validate(&self) -> Result<(), String> {
        let o = &self.omnidirectional;
        if [self.radius_m, self.differential_track_m, o.center_radius_m]
            .iter()
            .any(|v| !v.is_finite() || *v <= 0.0)
            || o.geometry_version != "radial_omni@1"
            || o.wheels.len() != 4
        {
            return Err("Invalid radial omni calibration".into());
        }
        let mut names = BTreeSet::new();
        let mut angles = vec![];
        for w in &o.wheels {
            if w.name.is_empty()
                || w.name.len() > 48
                || !w.name.bytes().enumerate().all(|(i, c)| {
                    c.is_ascii_lowercase() || (i > 0 && (c.is_ascii_digit() || c == b'_'))
                })
                || !names.insert(&w.name)
                || !w.azimuth_deg.is_finite()
                || !(0.0..360.0).contains(&w.azimuth_deg)
            {
                return Err("Invalid wheel name/azimuth".into());
            }
            angles.push(w.azimuth_deg);
        }
        angles.sort_by(f64::total_cmp);
        for i in 0..angles.len() {
            let gap = (angles[(i + 1) % angles.len()] - angles[i]).rem_euclid(360.0);
            // Only floating-point representation tolerance, not a physical tuning parameter.
            if (gap - 360.0 / angles.len() as f64).abs() > 360.0 * f64::EPSILON * 8.0 {
                return Err("Omni wheels must be 90 degrees apart".into());
            }
        }
        Ok(())
    }
    pub fn rates(&self, [vx, vy, wz]: [f64; 3], lateral: bool) -> Vec<f64> {
        if lateral {
            self.omnidirectional
                .wheels
                .iter()
                .map(|w| {
                    let a = w.azimuth_deg * TAU / 360.0;
                    (-a.sin() * vx + a.cos() * vy + self.omnidirectional.center_radius_m * wz)
                        / self.radius_m
                })
                .collect()
        } else {
            vec![
                (vx - wz * self.differential_track_m / 2.0) / self.radius_m,
                (vx + wz * self.differential_track_m / 2.0) / self.radius_m,
            ]
        }
    }
    pub fn names(&self, lateral: bool) -> Vec<&str> {
        if lateral {
            self.omnidirectional
                .wheels
                .iter()
                .map(|w| w.name.as_str())
                .collect()
        } else {
            vec!["left", "right"]
        }
    }
}
