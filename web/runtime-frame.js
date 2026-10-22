// This credential-free origin serves only fixed runtime artifacts. No workspace/config/Core routes.
let connected=false;
window.addEventListener("message",event=>{
  const uiOrigin=new URLSearchParams(location.search).get("ui");
  if(connected||event.source!==parent||event.origin!==uiOrigin||event.data!=="tankbot-runtime"||event.ports.length!==1)return;
  connected=true;
  const port=event.ports[0];let worker,timer,started,active=false,booting=false,limit,budget,qa=false,echoed=false;
  function stop(){clearTimeout(timer);worker?.terminate();worker=null;active=false;}
  function fault(code,detail=""){stop();port.postMessage({op:"fault",code,detail:String(detail).slice(0,256)});}
  port.onmessage=({data})=>{
    try{
      const {op,value}=JSON.parse(data);
      if(op==="conformance"&&qa&&!echoed){
        if(!Array.isArray(value)||value.length>64||value.some(v=>typeof v!=="string")||new TextEncoder().encode(data).length>limit)throw Error("QA frame limit");
        echoed=true;port.postMessage({op:"conformance",frames:value});return;
      }
      if(op==="close"){stop();return;}
      if(op==="init"){
        stop();limit=value.limit;budget=value.budget_ms;booting=true;qa=value.probe===true;
        worker=new Worker("/robot-worker.js");
        worker.onerror=event=>fault("MODULE_ERROR",event.message);
        worker.onmessage=({data:result})=>{
          if(result?.op==="progress"&&booting){port.postMessage({op:"progress",phase:result.phase});return;}
          if(result?.op==="fault"){fault("MODULE_ERROR",result.detail);return;}
          if(result?.op==="ready"&&booting){booting=false;clearTimeout(timer);port.postMessage({op:"ready",security:result.security,memory_bytes:result.memory_bytes});return;}
          if(!active||result?.op!=="result"||typeof result.raw!=="string"||new TextEncoder().encode(result.raw).length>limit){fault("RESOURCE_LIMIT");return;}
          active=false;clearTimeout(timer);
          port.postMessage({op:"result",raw:result.raw,elapsed_ms:performance.now()-started});
        };
        timer=setTimeout(()=>fault("RESOURCE_LIMIT","Startup deadline"),value.startup_timeout_s*1000);
        worker.postMessage({op,value:{...value,ui_origin:uiOrigin},sources:value.sources});
      }else if(op==="step"){
        if(active||!worker){fault("MODULE_ERROR");return;}
        active=true;started=performance.now();
        timer=setTimeout(()=>fault("RESOURCE_LIMIT"),budget);
        worker.postMessage({op,raw:JSON.stringify(value)});
      }else fault("UNAUTHORIZED");
    }catch(error){fault("INVALID_SCHEMA",String(error));}
  };
  port.start();port.postMessage({op:"bound"});
});
