let py, runner;
self.onmessage = async ({data}) => {
  try {
    if(data.op==="init") {
      self.postMessage({op:"progress",phase:"Pyodide"});
      importScripts("/pyodide/pyodide.js","/python-bootstrap.js");
      py = await self.tankbotPython("/player-bundle.json",false,loadPyodide);
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
      py.runPython("from module_runner import ModuleRunner, runtime_packages\nfrom source_loader import prepare\n_init=json.loads(_init_json)\n_temporary,_tests=prepare(_init)\nrunner=ModuleRunner(_init)\ndel _init_json");
      runner = py.globals.get("runner");
      self.postMessage({op:"ready",security,unit_tests:py.runPython("_tests"),runtime_packages:JSON.parse(py.runPython("json.dumps(runtime_packages())")),memory_bytes:py._module.HEAPU8.buffer.byteLength});
    } else if(data.op==="probe_ping") {
      self.postMessage({op:"probe_pong"});
    } else if(data.op==="step") {
      py.globals.set("_step_json",data.raw);
      const raw=py.runPython("json.dumps(runner.step(json.loads(_step_json)),allow_nan=False)");
      self.postMessage({op:"result",raw});
    }
  } catch(error) { self.postMessage({op:"fault",code:"MODULE_ERROR",detail:String(error).slice(-256)}); }
};
