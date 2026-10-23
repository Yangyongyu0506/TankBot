// Credential-free runtime origin: one isolated Worker per active/staging deployment.
let connected=false;
window.addEventListener("message",event=>{
  const uiOrigin=new URLSearchParams(location.search).get("ui");
  if(connected||event.source!==parent||event.origin!==uiOrigin||event.data!=="tankbot-runtime"||event.ports.length!==1)return;
  connected=true;
  const port=event.ports[0], workers=new Map();let qa=false,echoed=false,limit;
  port.onmessage=({data})=>{
    let worker_id;
    try{
      const message=JSON.parse(data),{op,value}=message;worker_id=message.worker_id;
      if(op==="conformance"&&qa&&!echoed){
        if(!Array.isArray(value)||value.length>64||value.some(v=>typeof v!=="string")||new TextEncoder().encode(data).length>limit)throw Error("QA frame limit");
        echoed=true;port.postMessage({op:"conformance",frames:value});return;
      }
      const old=workers.get(worker_id);
      if(op==="close"){old?.stop();return;}
      if(op==="init"){
        if(old||workers.size>=2)throw Error("Runtime slot limit");
        limit=value.limit;qa ||= value.probe===true;
        const state={worker:new Worker("/robot-worker.js"),active:false,booting:true,timer:null,started:0};
        const emit=v=>port.postMessage({...v,worker_id});
        state.stop=()=>{clearTimeout(state.timer);state.worker.terminate();workers.delete(worker_id);};
        state.fault=(code,detail="")=>{state.stop();emit({op:"fault",code,detail:String(detail).slice(0,256)});};
        workers.set(worker_id,state);
        state.worker.onerror=e=>state.fault("MODULE_ERROR",e.message);
        state.worker.onmessage=({data:result})=>{
          if(workers.get(worker_id)!==state)return;
          if(result?.op==="progress"&&state.booting){emit({op:"progress",phase:result.phase});return;}
          if(result?.op==="fault"){state.fault("MODULE_ERROR",result.detail);return;}
          if(result?.op==="ready"&&state.booting){state.booting=false;clearTimeout(state.timer);emit({op:"ready",security:result.security,memory_bytes:result.memory_bytes,unit_tests:result.unit_tests});return;}
          if(!state.active||result?.op!=="result"||typeof result.raw!=="string"||new TextEncoder().encode(result.raw).length>value.limit){state.fault("RESOURCE_LIMIT");return;}
          state.active=false;clearTimeout(state.timer);emit({op:"result",raw:result.raw,elapsed_ms:performance.now()-state.started});
        };
        state.timer=setTimeout(()=>state.fault("RESOURCE_LIMIT","Startup deadline"),value.startup_timeout_s*1000);
        state.worker.postMessage({op,value:{...value,ui_origin:uiOrigin},sources:value.sources});
        state.budget=value.budget_ms;
      }else if(op==="step"){
        if(!old||old.active||old.booting)throw Error("Runtime not ready");
        old.active=true;old.started=performance.now();
        old.timer=setTimeout(()=>old.fault("RESOURCE_LIMIT"),old.budget);
        old.worker.postMessage({op,raw:JSON.stringify(value)});
      }else throw Error("Unknown operation");
    }catch(error){
      workers.get(worker_id)?.stop();port.postMessage({op:"fault",worker_id,code:"INVALID_SCHEMA",detail:String(error).slice(0,256)});
    }
  };
  port.start();port.postMessage({op:"bound"});
});
