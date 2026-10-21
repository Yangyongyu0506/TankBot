// Trusted headless build probe. This is not a browser player API.
import {readFileSync} from "node:fs";
const path = process.argv[2] ?? "target/wasm32-unknown-unknown/debug/tankbot_core.wasm";
const bytes = readFileSync(path);
const {instance} = await WebAssembly.instantiate(bytes, {});
const x = instance.exports.tankbot_m1_probe();
if (!Number.isFinite(x)) throw new Error("Non-finite probe result");
console.log(JSON.stringify({wasm_bytes: bytes.length, final_x_m: x}));
