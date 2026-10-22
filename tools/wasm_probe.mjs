// Trusted headless build probe. This is not a browser player API.
import {readFileSync} from "node:fs";
const path = process.argv[2] ?? "target/wasm32-unknown-unknown/debug/tankbot_core.wasm";
const bytes = readFileSync(path);
const {instance} = await WebAssembly.instantiate(bytes, {});
const x = instance.exports.tankbot_m1_probe();
if (!Number.isFinite(x)) throw new Error("Non-finite probe result");
const shots = instance.exports.tankbot_m1b_probe();
const angle = instance.exports.tankbot_m1b_angle_probe();
if (!Number.isFinite(shots) || shots <= 0 || !Number.isFinite(angle)) throw new Error("Invalid weapon probe");
const wheel = instance.exports.tankbot_omni_wheel_probe();
if (!Number.isFinite(wheel)) throw new Error("Invalid omni wheel probe");
console.log(JSON.stringify({wasm_bytes: bytes.length, final_x_m: x, shots_fired: shots, relative_angle_rad: angle, omni_first_wheel_radps: wheel}));
