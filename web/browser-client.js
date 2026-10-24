// UI owns only a narrow control channel and authorized snapshots, never a Core/robot heap.
export async function connectBrowser(){
  const options=await (await fetch("/browser-profile.json")).json();
  const state=await (await fetch("/api/settings")).json();
  const session=await (await fetch("/api/session/start",{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":state.control_token},body:"{}"})).json();
  if(session.error)throw Error(session.error);
  const worker=new Worker("/core-worker.js",{type:"module"});
  const frame=document.createElement("iframe");frame.hidden=true;
  frame.sandbox="allow-scripts allow-same-origin";
  frame.src=options.runtime_origin+"/runtime-frame.html?ui="+encodeURIComponent(location.origin);
  const loaded=new Promise(resolve=>frame.addEventListener("load",resolve,{once:true}));
  document.body.append(frame);await loaded;
  const channel=new MessageChannel();
  frame.contentWindow.postMessage("tankbot-runtime",options.runtime_origin,[channel.port2]);
  const pending=new Map();let serial=0,view,profile,health,failed;
  let resolveProfile,rejectProfile,completion=null,completionError=null;
  const boot=new Promise((resolve,reject)=>{resolveProfile=resolve;rejectProfile=reject;});
  const dispose=()=>{worker.terminate();frame.remove();for(const entry of pending.values()){clearTimeout(entry.timer);entry.resolve({ok:false,json:async()=>({error:"CANCELLED"})});}pending.clear();};
  const fail=message=>{failed=message;clearTimeout(startup);rejectProfile(Error(failed));dispose();};
  const startup=setTimeout(()=>fail("浏览器 Runtime 启动超时"),options.startup_timeout_s*1000*2);
  worker.onmessage=({data})=>{
    if(data.kind==="progress")document.getElementById("connection").textContent="正在加载 "+data.value+"…";
    else if(data.kind==="profile"){profile=data.value;clearTimeout(startup);resolveProfile(profile);}
    else if(data.kind==="view")view=data.value;
    else if(data.kind==="health")health=data.value;
    else if(data.kind==="completed"){
      completion=data.value;
      persistCompletion();
    }
    else if(data.kind==="error")fail(data.value);
    else if(data.kind==="response"){
      const entry=pending.get(data.id);if(entry){pending.delete(data.id);clearTimeout(entry.timer);entry.resolve({ok:data.ok,json:async()=>data.value});}
    }
  };
  worker.onerror=()=>fail("Core Worker 已停止");
  async function persistCompletion(){
    if(!completion||!session.ticket)return;
    try{
      const response=await fetch("/api/progress/complete",{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":state.control_token},body:JSON.stringify({ticket:session.ticket,level_id:session.level_id})});
      const result=await response.json();if(!response.ok)throw Error(result.error);
      completion=null;completionError=null;
    }catch(error){completionError="通关存档失败："+error.message;}
  }
  worker.postMessage({op:"start",port:channel.port1,developerMode:session.developer_mode},[channel.port1]);
  await boot;
  const client={profile,
    view:async()=>{if(failed||!view)throw Error(failed||"Waiting for view");return structuredClone(view);},
    health:()=>health,
    saveError:()=>completionError,
    retrySave:persistCompletion,
    post:async(path,value)=>{
      if(path==="/api/developer"){
        const current=await (await fetch("/api/settings")).json();
        if(!session.developer_mode||!current.settings.developer_mode)return {ok:false,json:async()=>({error:"UNAUTHORIZED"})};
      }
      if(failed||pending.size>=options.max_pending_requests)return Promise.resolve({ok:false,json:async()=>({})});
      return new Promise(resolve=>{const id=serial++;const timer=setTimeout(()=>{pending.delete(id);resolve({ok:false,json:async()=>({})});},options.startup_timeout_s*1000);
        pending.set(id,{resolve,timer});worker.postMessage({op:"command",path,value,id});});
    },
    close:()=>{clearTimeout(startup);dispose();}
  };
  // Explicit local QA sees only the same authorized snapshot/control adapter as this UI.
  if(options.probe_enabled)window.tankbotQA=Object.freeze({
    view:async()=>JSON.stringify(await client.view()),
    post:async(path,value)=>{const response=await client.post(path,value);return JSON.stringify({ok:response.ok,value:await response.json()});}
  });
  return client;
}
