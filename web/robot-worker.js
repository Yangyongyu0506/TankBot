let py, runner;
let logBytes=0,logLines=0,logLimit=0,logTruncated=false;
function output(line){
  if(logLines>=128||logBytes>=logLimit){if(!logTruncated){logTruncated=true;self.postMessage({op:"log",text:"[输出过多，本批次剩余日志已省略]\n"});}return;}
  const text=String(line).slice(0,2047)+"\n",bytes=new TextEncoder().encode(text).length;
  if(logBytes+bytes>logLimit){logBytes=logLimit;logTruncated=true;self.postMessage({op:"log",text:"[输出过多，本批次剩余日志已省略]\n"});return;}
  logBytes+=bytes;logLines++;self.postMessage({op:"log",text});
}
self.onmessage = async ({data}) => {
  try {
    if(data.op==="init") {
      logLimit=Math.min(data.value.max_log_bytes, data.value.limit/2);
      self.postMessage({op:"progress",phase:"Pyodide"});
      importScripts("/pyodide/pyodide.js","/python-bootstrap.js");
      py = await self.tankbotPython("/player-bundle.json",false,loadPyodide,output);
      let security=null;
      if(data.value.probe){
        py.globals.set("_ui_origin",data.value.ui_origin);
        py.globals.set("_probe_timeout_s",data.value.startup_timeout_s);
        security=JSON.parse(await py.runPythonAsync(`
from pathlib import Path
from pyodide.http import pyfetch
from pyodide.ffi import create_proxy
import asyncio, js, json, os
checks={"no_core_handle":not hasattr(js,"core_call"),
        "no_authority_files":not Path('/tankbot/host').exists(),
        "no_private_config":not Path('/tankbot/config/m1.json').exists(),
        "no_host_files":not Path('/etc/passwd').exists()}
for label,url in [('ui_network_blocked',_ui_origin+'/api/view'),('external_network_blocked','https://example.com/')]:
    try:
        await pyfetch(url)
        checks[label]=False
    except Exception:
        checks[label]=True
try:
    worker=js.Worker.new('/robot-worker.js')
    future=asyncio.get_running_loop().create_future()
    def blocked(event):
        event.preventDefault()
        if not future.done(): future.set_result(True)
    def executed(event):
        if not future.done(): future.set_result(False)
    onerror,onmessage=create_proxy(blocked),create_proxy(executed)
    worker.onerror,worker.onmessage=onerror,onmessage
    worker.postMessage(js.JSON.parse('{"op":"probe_ping"}'))
    try:
        checks['nested_worker_blocked']=await asyncio.wait_for(future,_probe_timeout_s)
    finally:
        worker.terminate()
        onerror.destroy()
        onmessage.destroy()
except Exception:
    checks['nested_worker_blocked']=True
try:
    os.fork()
    checks['fork_unavailable']=False
except (AttributeError, OSError):
    checks['fork_unavailable']=True
json.dumps(checks)
`));
      }
      self.postMessage({op:"progress",phase:"Module initialization"});
      const init={...data.value.init,sources:data.value.init.sources??data.sources};
      py.globals.set("_init_json",JSON.stringify(init));
      py.runPython("from module_runner import ModuleRunner, runtime_packages\nfrom source_loader import prepare, PlayerTestsFailed\nimport traceback\n_init=json.loads(_init_json)\ntry:\n _temporary,_tests=prepare(_init)\n runner=ModuleRunner(_init)\nexcept Exception as _error:\n if not isinstance(_error,PlayerTestsFailed):\n  traceback.print_exc(file=sys.stderr)\n raise\ndel _init_json");
      runner = py.globals.get("runner");
      self.postMessage({op:"ready",security,unit_tests:py.runPython("_tests"),runtime_packages:JSON.parse(py.runPython("json.dumps(runtime_packages())")),memory_bytes:py._module.HEAPU8.buffer.byteLength});
    } else if(data.op==="probe_ping") {
      self.postMessage({op:"probe_pong"});
    } else if(data.op==="step") {
      logBytes=0;logLines=0;logTruncated=false;
      py.globals.set("_step_json",data.raw);
      const raw=py.runPython("try:\n _result=runner.step(json.loads(_step_json))\n _raw=json.dumps(_result,allow_nan=False)\nexcept Exception:\n traceback.print_exc(file=sys.stderr)\n raise\n_raw");
      self.postMessage({op:"result",raw});
    }
  } catch(error) { self.postMessage({op:"fault",code:"MODULE_ERROR",detail:String(error).slice(-256)}); }
};
