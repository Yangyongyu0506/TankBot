import {WasmCore} from "/wasm-core.js";
import {python} from "/python-loader.js";
let py, authority, ready=false, timer, config, runtimePort, coldStart,security,playerMemory,fixtures;
const coreTimes=[];
const distribution=values=>{const a=[...values].sort((x,y)=>x-y);return {count:a.length,p50_ms:a[Math.floor(a.length*.5)],p95_ms:a[Math.floor(a.length*.95)],max_ms:a.at(-1)};};
const notify=(kind,value)=>self.postMessage({kind,value});
function evaluate(code){return JSON.parse(py.runPython(`json.dumps(${code},allow_nan=False)`));}
function tick(){
  if(!ready)return;
  const started=performance.now();
  try{
    py.runPython("authority.advance()");
    const n=evaluate("authority.tick");
    if(n%(config.clock.physics_hz/config.view.snapshot_hz)===0)notify("view",evaluate("authority.view"));
    if(n%config.clock.physics_hz===0)notify("health",{...evaluate("diagnostics(authority)"),worker_startup_ms:coldStart,security,player_memory_bytes:playerMemory,fixtures,core_call_cost:distribution(coreTimes),
      core_memory_bytes:core.exports.memory.buffer.byteLength,authority_memory_bytes:py._module.HEAPU8.buffer.byteLength});
  }catch(error){ready=false;notify("error",String(error));return;}
  // Fixed simulation dt, yielding between every boundary. Never await the robot. No RAF coupling.
  deadline+=1000/config.clock.physics_hz;
  if(performance.now()-deadline>config.host.max_catchup_ticks*1000/config.clock.physics_hz)deadline=performance.now();
  timer=setTimeout(tick,Math.max(0,deadline-performance.now()));
}
let core,deadline;
let starting=false;
self.onmessage=async({data})=>{
  if(!data||typeof data!=="object")return;
  try{
    if(data.op==="start"){
      if(starting)throw Error("Core Worker already initialized");
      starting=true;
      const started=performance.now();runtimePort=data.port;
      runtimePort.onmessage=({data:result})=>{
        if(!py)return;
        if(result.op==="conformance"&&config.browser.probe_enabled){
          py.globals.set("_fixture_frames_json",JSON.stringify(result.frames));
          py.runPython("_frames=json.loads(_fixture_frames_json)\nassert len(_frames)==len(_fixture_cases)\nassert all(strict_loads(raw)==c['message'] for raw,c in zip(_frames,_fixture_cases))\n_fixture_results=[dict(id=c['id'],verdict=verdict(c,authority.config,strict_loads(raw)),expected=c['expected']) for raw,c in zip(_frames,_fixture_cases)]");
          fixtures=evaluate("_fixture_results");
        }
        else if(result.op==="progress"){notify("progress",String(result.phase).slice(0,64));}
        else if(result.op==="ready"&&!ready){
          security=result.security;playerMemory=result.memory_bytes;
          coldStart=performance.now()-started;ready=true;deadline=performance.now();
          notify("profile",evaluate("authority.public_profile()"));tick();
        }else if(result.op==="result"){
          py.globals.set("_raw",result.raw);py.globals.set("_elapsed",result.elapsed_ms);
          py.runPython("authority.worker.receive(_raw,_elapsed)");
        }else if(result.op==="fault"){
          py.runPython("authority.worker.fault='RESOURCE_LIMIT'\nauthority.worker.close()");
          if(!ready)notify("error","Python runtime initialization failed: "+result.code+" "+result.detail);
        }
      };runtimePort.start();
      const [bytes,conf,sources]=await Promise.all([
        fetch("/tankbot_core.wasm").then(r=>r.arrayBuffer()),fetch("/authority-config.json").then(r=>r.json()),
        fetch("/deployment.json").then(r=>r.json())]);config=conf;
      core=new WasmCore((await WebAssembly.instantiate(bytes,{})).instance);
      self.core_call=raw=>{const request=JSON.parse(raw),t=performance.now();const response=core.call(request);
        if(request.op==="step"){coreTimes.push(performance.now()-t);if(coreTimes.length>config.runtime.history_limit_ticks)coreTimes.shift();}return response;};
      self.runtime_send=raw=>{
        const msg=JSON.parse(raw);
        if(msg.op==="init")msg.value.sources=sources;
        runtimePort.postMessage(JSON.stringify(msg));
      };
      py=await python("/authority-bundle.json",true);
      py.FS.mkdirTree("/tankbot/config");py.FS.writeFile("/tankbot/config/m1.json",JSON.stringify(config));
      py.runPython("from browser_authority import start, diagnostics\nauthority=start()");
      if(config.browser.probe_enabled){
        py.runPython("from tankbot_protocol.conformance import cases, verdict\nfrom tankbot_protocol.wire import strict_loads\n_fixture_cases=cases('/tankbot/docs/examples')");
        runtimePort.postMessage(JSON.stringify({op:"conformance",value:evaluate("[json.dumps(c['message']) for c in _fixture_cases]")}));
      }
      authority=true;
    }else if(data.op==="command"&&authority){
      py.globals.set("_command",JSON.stringify(data.value));
      const method={"/api/cmd_vel":"keyboard","/api/turret_cmd_vel":"turret_keyboard","/api/fire":"fire_keyboard"}[data.path];
      if(!method)throw Error("UNAUTHORIZED");
      py.runPython(`_reply=authority.${method}(json.loads(_command))`);
      self.postMessage({kind:"response",id:data.id,ok:true,value:evaluate("_reply")});
    }
  }catch(error){
    if(data.id!==undefined)self.postMessage({kind:"response",id:data.id,ok:false});
    else notify("error",String(error));
  }
};
