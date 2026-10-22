// UI owns only a narrow control channel and authorized snapshots, never a Core/robot heap.
export async function connectBrowser(){
  const options=await (await fetch("/browser-profile.json")).json();
  const worker=new Worker("/core-worker.js",{type:"module"});
  const frame=document.createElement("iframe");frame.hidden=true;
  frame.sandbox="allow-scripts allow-same-origin";
  frame.src=options.runtime_origin+"/runtime-frame.html?ui="+encodeURIComponent(location.origin);
  const loaded=new Promise(resolve=>frame.addEventListener("load",resolve,{once:true}));
  document.body.append(frame);await loaded;
  const channel=new MessageChannel();
  frame.contentWindow.postMessage("tankbot-runtime",options.runtime_origin,[channel.port2]);
  const pending=new Map();let serial=0,view,profile,health,failed;
  let resolveProfile,rejectProfile;
  const boot=new Promise((resolve,reject)=>{resolveProfile=resolve;rejectProfile=reject;});
  const dispose=()=>{worker.terminate();frame.remove();for(const entry of pending.values()){clearTimeout(entry.timer);entry.resolve({ok:false});}pending.clear();};
  const fail=message=>{failed=message;clearTimeout(startup);rejectProfile(Error(failed));dispose();};
  const startup=setTimeout(()=>fail("浏览器 Runtime 启动超时"),options.startup_timeout_s*1000*2);
  worker.onmessage=({data})=>{
    if(data.kind==="progress")document.getElementById("connection").textContent="正在加载 "+data.value+"…";
    else if(data.kind==="profile"){profile=data.value;clearTimeout(startup);resolveProfile(profile);}
    else if(data.kind==="view")view=data.value;
    else if(data.kind==="health")health=data.value;
    else if(data.kind==="error")fail(data.value);
    else if(data.kind==="response"){
      const entry=pending.get(data.id);if(entry){pending.delete(data.id);clearTimeout(entry.timer);entry.resolve({ok:data.ok,json:async()=>data.value});}
    }
  };
  worker.onerror=()=>fail("Core Worker 已停止");
  worker.postMessage({op:"start",port:channel.port1},[channel.port1]);
  await boot;
  return {profile,
    view:async()=>{if(failed||!view)throw Error(failed||"Waiting for view");return structuredClone(view);},
    health:()=>health,
    post:(path,value)=>{
      if(failed||pending.size>=options.max_pending_requests)return Promise.resolve({ok:false,json:async()=>({})});
      return new Promise(resolve=>{const id=serial++;const timer=setTimeout(()=>{pending.delete(id);resolve({ok:false,json:async()=>({})});},options.startup_timeout_s*1000);
        pending.set(id,{resolve,timer});worker.postMessage({op:"command",path,value,id});});
    },
    close:()=>{clearTimeout(startup);dispose();}
  };
}
