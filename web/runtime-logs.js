// Player stdout/errors only. The source identity and bounded retention come from Authority.
export function mountRuntimeLogs(browser,profile){
  const $=id=>document.getElementById(id),roots=[$("hud-runtime-log-view"),$("editor-runtime-log-view")];
  let state={entries:[],next_sequence:0,dropped:0},runId,clearedThrough=0;
  const names={runtime:"当前程序",test:"测试快照",deploy:"部署启动",rollback:"回滚启动"};
  const views=roots.map(root=>{
    const toolbar=document.createElement("div"),filter=document.createElement("select"),clear=document.createElement("button"),status=document.createElement("span"),output=document.createElement("div");
    toolbar.className="runtime-log-toolbar";output.className="runtime-log-output";output.setAttribute("role","log");output.setAttribute("aria-label","玩家程序日志");
    filter.setAttribute("aria-label","日志来源");
    for(const [value,text] of Object.entries({all:"全部来源",...names})){const option=document.createElement("option");option.value=value;option.textContent=text;filter.append(option);}
    clear.type="button";clear.textContent="清空显示";status.className="hint";status.setAttribute("role","status");
    toolbar.append(filter,clear,status);root.append(toolbar,output);
    const view={root,filter,status,output,key:""};
    filter.onchange=()=>{view.key="";render(view);};
    clear.onclick=()=>{clearedThrough=state.next_sequence;for(const panel of views){panel.key="";render(panel);}};
    return view;
  });
  function render(view){
    const key=[state.next_sequence,clearedThrough,view.filter.value].join(":");if(key===view.key)return;view.key=key;
    const follow=view.output.scrollHeight-view.output.scrollTop-view.output.clientHeight<40;
    const entries=state.entries.filter(entry=>entry.sequence>=clearedThrough&&(view.filter.value==="all"||entry.source===view.filter.value));
    view.output.replaceChildren(...entries.map(entry=>{
      const row=document.createElement("div"),label=document.createElement("small"),pre=document.createElement("pre");row.className="runtime-log-entry";row.dataset.stream=entry.stream;
      label.textContent=`${names[entry.source]??entry.source} · ${entry.module_id} · ${(entry.deployment_id??"startup").slice(0,8)} · 接收 tick ${entry.tick}`;pre.textContent=entry.text;row.append(label,pre);
      const match=entry.text.match(/File ["']([^"']+\.py)["'], line (\d+)|([A-Za-z_][\w/]*\.py):(\d+):/);
      if(match&&!/^(runtime\/|sdk\/|\/)/.test(match[1]??match[3])){
        const path=match[1]??match[3],line=Number(match[2]??match[4]),button=document.createElement("button");button.type="button";button.textContent=`打开 ${path}:${line}`;
        button.title="定位到当前编辑文件；如果修改过源码，行号可能与该日志版本不同。";
        button.onclick=()=>window.dispatchEvent(new CustomEvent("tankbot-open-source",{detail:{path,line,revision:entry.revision}}));row.append(button);
      }
      return row;
    }));
    if(!entries.length){const hint=document.createElement("p");hint.className="hint";hint.textContent="暂无输出。可在算法中使用 print()；异常与测试反馈也会显示在这里。";view.output.append(hint);}
    view.status.textContent=`${entries.length} 条 · 最近 ${Math.round((state.max_bytes??0)/1024)} KiB${state.dropped?" · 较早日志已省略":""}`;
    if(follow)view.output.scrollTop=view.output.scrollHeight;
    view.root.dataset.count=entries.length;
  }
  $("toggle-editor-logs").onclick=()=>{
    const panel=$("editor-runtime-logs"),open=panel.hidden;panel.hidden=!open;$("toggle-editor-logs").setAttribute("aria-expanded",String(open));
    if(open)views[1].output.scrollTop=views[1].output.scrollHeight;
  };
  $("tab-logs").addEventListener("click",()=>{views[0].output.scrollTop=views[0].output.scrollHeight;});
  async function poll(){
    try{
      const response=browser?await browser.post("/api/deployment",{}):await fetch("/api/deployment");
      const result=await response.json();if(!response.ok)throw Error(result.error??"读取日志失败");
      if(runId!==result.run_id){runId=result.run_id;clearedThrough=0;}
      state=result.logs??state;for(const view of views)render(view);
      const errors=state.entries.some(entry=>entry.sequence>=clearedThrough&&entry.stream==="error");
      $("tab-logs").classList.toggle("has-error",errors);$("tab-logs").title=errors?"程序或测试有错误，点击查看日志":"查看玩家程序输出与错误";
    }catch{for(const view of views){view.key="";view.status.textContent="暂时无法读取日志，正在重试…";}}
    setTimeout(poll,Math.max(250,profile.view.poll_ms*10));
  }
  poll();
}
