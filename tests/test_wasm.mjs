import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {spawn} from "node:child_process";
import {WasmCore} from "../web/wasm-core.js";

const bytes=readFileSync(new URL("../target/wasm32-unknown-unknown/release/tankbot_core.wasm",import.meta.url));
const wasm=new WasmCore((await WebAssembly.instantiate(bytes,{})).instance);
const child=spawn(new URL("../target/debug/core_worker",import.meta.url).pathname,[],{stdio:["pipe","pipe","inherit"]});
let buffer=Buffer.alloc(0),receive;
child.stdout.on("data",raw=>{buffer=Buffer.concat([buffer,raw]);if(buffer.length>=4&&buffer.length>=4+buffer.readUInt32BE(0)){
  const length=buffer.readUInt32BE(0),reply=JSON.parse(buffer.subarray(4,4+length));buffer=buffer.subarray(4+length);receive(reply);
}});
function native(request){return new Promise(resolve=>{receive=resolve;const raw=Buffer.from(JSON.stringify(request)),head=Buffer.alloc(4);head.writeUInt32BE(raw.length);child.stdin.write(Buffer.concat([head,raw]));});}
try{
  const config=JSON.parse(readFileSync(new URL("../config/m1.json",import.meta.url)));
  const exchange=async request=>{
    const a=JSON.parse(wasm.call(request)),b=await native(request);
    // Empirical same-toolchain equivalence, not a cross-platform bitwise guarantee.
    assert.deepEqual(a,b);return a;
  };
  for(const chassis of ["differential","omnidirectional"]){
    assert.equal((await exchange({op:"init",config,chassis})).ok,true);
    for(let tick=0;tick<config.validation.ticks;tick++){
      const request={op:"step",target:tick%6===0?{vx:.5,vy:chassis==="omnidirectional"?.3:0,wz:.2,source_tick:tick}:null,
        turret_target:tick%6===0?{velocity_radps:2,source_tick:tick}:null,
        fire_requests:tick%18===0?[{publisher_id:"probe",request_id:`shot-${tick}`,source_tick:tick}]:[]};
      const result=await exchange(request);assert.equal(result.ok,true);
    }
    assert.equal((await exchange({op:"snapshot"})).data.tick,600);
  }
  const campaign=structuredClone(config);
  campaign.weapons.targets=[campaign.campaign.levels.c2.target];
  assert.equal((await exchange({op:"init",config:campaign,chassis:"omnidirectional"})).ok,true);
  for(let tick=0;tick<1800;tick++){
    const result=await exchange({op:"step",turret_target:tick%6===0?{velocity_radps:1,source_tick:tick}:null,
      fire_requests:tick%18===0?[{publisher_id:"probe",request_id:`campaign-${tick}`,source_tick:tick}]:[]});
    assert.equal(result.ok,true);
    assert.equal(result.data.targets.length,1);
  }
  assert.equal((await native({op:"invalid"})).ok,false);
  assert.equal(JSON.parse(wasm.call({op:"invalid"})).ok,false);
  assert.equal(wasm.exports.tankbot_input(1024*1024+1),0);
  console.log("PASS: shared JSON ABI, 2 × 600 weapon + 1800 campaign native/WASM snapshots, invalid operation and buffer limit");
}finally{child.stdin.end();}
