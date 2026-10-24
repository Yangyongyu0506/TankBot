// Workspace changes are explicit revisions; renderer and input controls do not own player code.
import {mountLearning} from "/learning-ui.js";
export function setupWorkspaceDialog(releaseControls){
  const dialog=document.getElementById("workspace-dialog"),toggle=document.getElementById("open-workspace");
  let previousFocus,editorFocus;
  function show(){
    previousFocus=document.activeElement;
    releaseControls();
    dialog.showModal();
    toggle.setAttribute("aria-expanded","true");
    const help=dialog.querySelector("#learning-pane:not([hidden]) #learning-title");
    const focus=innerWidth<1050&&help?help:editorFocus?.isConnected?editorFocus:dialog.querySelector(".cm-content");
    focus?.focus({preventScroll:true});
  }
  function hide(){if(dialog.open)dialog.close();}
  toggle.addEventListener("click",()=>dialog.open?hide():show());
  document.getElementById("close-workspace").addEventListener("click",hide);
  dialog.addEventListener("beforetoggle",event=>{
    if(event.newState==="closed"&&dialog.contains(document.activeElement))editorFocus=document.activeElement;
  });
  dialog.addEventListener("close",()=>{
    toggle.setAttribute("aria-expanded","false");
    const focus=previousFocus?.isConnected&&previousFocus!==document.body?previousFocus:document.getElementById("arena");
    focus.focus({preventScroll:true});
  });
  dialog.addEventListener("cancel",event=>{
    event.preventDefault();
    // Escape belongs to CodeMirror/Vim while editing; F2 always toggles the dialog.
    if(!document.activeElement?.closest(".cm-editor"))hide();
  });
  window.addEventListener("keydown",event=>{
    if(event.code!=="F2"||event.ctrlKey||event.metaKey||event.altKey||event.shiftKey||event.isComposing)return;
    event.preventDefault();event.stopImmediatePropagation();
    if(!event.repeat)(dialog.open?hide():show());
  },{capture:true});
}

export async function mountWorkspace(browser){
  const $=id=>document.getElementById(id),root=$("workspace-panel");
  let snapshot,files,selected,editor,plan,status,busy=false,token,level,learning;
  const message=text=>{$("workspace-message").textContent=text;};
  const dirty=()=>JSON.stringify(files)!==JSON.stringify(snapshot.files);
  async function http(operation,value){
    const r=await fetch("/api/workspace/"+operation,{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":token},body:JSON.stringify(value)});
    const result=await r.json();if(!r.ok)throw Error(result.error||"Workspace request failed");return result;
  }
  async function runtime(operation,value={}){
    if(!browser&&["test","deploy"].includes(operation))value={revision:value.revision};
    const path="/api/deployment"+(operation?"/"+operation:"");
    const r=browser?await browser.post(path,value):await fetch(path,operation?{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":token},body:JSON.stringify(value)}:undefined);
    const result=await r.json();if(!r.ok)throw Error(result.error||"Deployment request failed");return result;
  }
  function refresh(){
    root.dataset.busy=String(busy);
    root.dataset.dirty=String(dirty());
    root.dataset.runtimeBusy=String(Boolean(status?.job));
    root.dataset.revision=snapshot.revision;
    $("workspace-revision").textContent=(dirty()?"未保存 · ":"已保存 · ")+snapshot.revision.slice(0,12);
    $("file-list").replaceChildren(...Object.keys(files).sort().map(path=>{
      const button=document.createElement("button");button.type="button";button.textContent=path+(files[path]!==snapshot.files[path]?" *":"");button.title=path;button.classList.toggle("selected",path===selected);
      button.onclick=()=>open(path);return button;
    }));
    $("save-workspace").disabled=busy||!dirty();
    $("test-workspace").disabled=busy||Boolean(status?.job);
    $("deploy-workspace").disabled=busy||dirty()||Boolean(status?.job)||!status?.reports.some(r=>r.revision===snapshot.revision&&r.status==="Ready");
    $("rollback-workspace").disabled=busy||Boolean(status?.job)||!$("deployment-history").value;
  }
  function open(path){selected=path;$("editor-path").textContent=path;editor.open(path,files[path]);learning?.file(path);refresh();}
  function accept(value){snapshot=value;files={...value.files};const preferred=level==="c2"?"perception/tracker.py":level==="c1"?"perception/transforms.py":level==="c0"?"campaign_robot.py":null;open(files[selected]!==undefined?selected:(preferred&&preferred in files?preferred:Object.keys(files).find(p=>p.endsWith("odometry.py"))||Object.keys(files)[0]));}
  async function save(){
    const changes={};for(const p of new Set([...Object.keys(files),...Object.keys(snapshot.files)]))if(files[p]!==snapshot.files[p])changes[p]=files[p]??null;
    if(Object.keys(changes).length)accept(await http("save",{revision:snapshot.revision,changes}));
    message("已保存。当前运行版本保持原样。");
  }
  async function action(fn){if(busy)return;busy=true;refresh();try{await fn();}catch(error){message(error.message);locate(error.message);}finally{busy=false;refresh();}}
  function locate(text){const match=text.match(/([A-Za-z_][\w/]*\.py):(\d+):/);if(match&&files[match[1]]!==undefined){open(match[1]);editor.go(Number(match[2]));}}
  function showPlan(value){
    plan=value;$("migration-panel").hidden=false;$("migration-list").replaceChildren();
    for(const entry of plan.entries){
      const detail=document.createElement("details"),summary=document.createElement("summary");summary.textContent=entry.path+" · "+(entry.action==="create"?"新增":"已有文件：默认保留");detail.append(summary);
      const row=document.createElement("div");row.className="migration-columns";
      for(const [label,text] of [["旧模板",entry.base],["当前内容",entry.current],["新建议",entry.incoming]]){
        const column=document.createElement("div"),heading=document.createElement("strong"),pre=document.createElement("pre");heading.textContent=label;pre.textContent=text??"（无）";column.append(heading,pre);row.append(column);
      }
      detail.append(row);
      if(entry.action==="conflict"){
        const select=document.createElement("select");select.dataset.path=entry.path;
        for(const [value,label] of [["keep","保留当前文件"],["incoming","明确采用新建议（旧 revision 仍保留）"]]){const option=document.createElement("option");option.value=value;option.textContent=label;select.append(option);}detail.append(select);
      }
      $("migration-list").append(detail);
    }
    message(plan.already_applied?"此模板已应用；再次预览不会覆盖文件。":"请检查新增文件与冲突，再应用。可先在编辑器手动合并后重新预览。");
  }
  const initial=await (await fetch("/api/workspace")).json();token=initial.control_token;level=initial.level_id;snapshot=initial.snapshot;files={...snapshot.files};
  const {createEditor}=await import("/editor-bundle.js");
  editor=createEditor($("code-editor"),(path,text)=>{files[path]=text;refresh();},()=>action(save),initial.learning);
  learning=mountLearning(initial.learning,open,()=>$("template-workspace").click());
  accept(snapshot);
  $("save-workspace").onclick=()=>action(save);
  $("test-workspace").onclick=()=>action(async()=>{await save();status=await runtime("test",{revision:snapshot.revision,snapshot});message("正在独立运行环境中测试此快照…");});
  $("deploy-workspace").onclick=()=>action(async()=>{status=await runtime("deploy",{revision:snapshot.revision,snapshot});message("正在启动候选版本，成功后切换…");});
  $("rollback-workspace").onclick=()=>action(async()=>{status=await runtime("rollback",{sha256:$("deployment-history").value});message("正在以干净状态重新部署所选版本…");});
  $("new-file").onclick=()=>action(async()=>{
    const path=$("new-file-path").value.trim();if(!path)throw Error("输入相对路径，例如 planning/controller.py");
    if(Object.keys(files).some(p=>p.toLowerCase()===path.toLowerCase()))throw Error("文件已存在，请直接选择编辑");
    // Server validation happens before adding any draft file; unsaved work is preserved first.
    await save();accept(await http("save",{revision:snapshot.revision,changes:{[path]:path.endsWith(".py")?"# 在这里实现你的算法。\n":""}}));open(path);$("new-file-path").value="";
  });
  $("vim-mode").onchange=e=>editor.vim(e.target.checked);
  $("template-workspace").onclick=()=>action(async()=>{await save();showPlan(await http("template",{revision:snapshot.revision}));});
  $("apply-migration").onclick=()=>action(async()=>{
    const resolutions={};$("migration-list").querySelectorAll("select[data-path]").forEach(e=>resolutions[e.dataset.path]=e.value);
    accept(await http("apply",{plan_id:plan.plan_id,revision:plan.base_revision,resolutions}));$("migration-panel").hidden=true;message("已创建新 revision；之前的 revision 可导出或恢复。");
  });
  $("select-framework-upgrade").onclick=()=>{
    $("migration-list").querySelectorAll("select[data-path]").forEach(select=>{select.value=initial.learning.managed_files.includes(select.dataset.path)?"incoming":"keep";});
    message("已选择系统脚手架；算法文件保留。请检查预览后点击应用。");
  };
  $("cancel-migration").onclick=()=>{$("migration-panel").hidden=true;plan=null;};
  $("export-workspace").onclick=()=>action(async()=>{
    await save();const url=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:"application/json"}));
    const a=document.createElement("a");a.href=url;a.download="tankbot-"+snapshot.revision.slice(0,12)+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $("export-records").onclick=()=>action(async()=>{
    const records=await http("archives",{}),url=URL.createObjectURL(new Blob([JSON.stringify(records,null,2)],{type:"application/json"}));
    const a=document.createElement("a");a.href=url;a.download="tankbot-deployment-records.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $("import-workspace").onchange=e=>action(async()=>{
    const file=e.target.files[0];if(!file)return;if(file.size>initial.limits.max_source_bytes*4)throw Error("导入文件超过限额");
    const value=JSON.parse(await file.text());await save();showPlan(await http("import",{revision:snapshot.revision,files:value.files}));e.target.value="";
  });
  $("restore-revision").onclick=()=>action(async()=>{await save();const value=await http("revision",{revision:$("revision-input").value.trim()});showPlan(await http("import",{revision:snapshot.revision,files:value.files}));});
  window.addEventListener("beforeunload",e=>{if(dirty()){e.preventDefault();e.returnValue="";}});
  let previousLast="";
  async function poll(){
    try{
      status=await runtime("");root.dataset.deployment=JSON.stringify(status);root.dataset.revision=snapshot.revision;
      $("active-deployment").textContent=status.active?status.active.sha256.slice(0,12)+" · tick "+status.active.activated_tick:"启动示例（尚未部署工作区）";
      $("deployment-state").textContent=status.job?(status.job.kind+" / "+status.job.phase):status.last?.status||"Editing";
      const history=$("deployment-history"),choice=history.value;
      history.replaceChildren(...[...new Map(status.history.map(d=>[d.sha256,d])).values()].map(d=>{const o=document.createElement("option");o.value=d.sha256;o.textContent=d.sha256.slice(0,12)+" · "+d.revision.slice(0,8);return o;}));
      if([...history.options].some(o=>o.value===choice))history.value=choice;
      if(status.last&&JSON.stringify(status.last)!==previousLast){previousLast=JSON.stringify(status.last);
        const last=status.last;
        message(last.status==="Failed"?"失败："+last.error:last.status==="Ready"?`测试通过：${last.unit_tests} 个单元测试，${last.simulation_batches} 个传感器仿真批次；摘要 ${last.sha256.slice(0,12)}`:`已激活 ${last.sha256.slice(0,12)}；物理世界继续运行。`);
        if(last.status==="Failed")locate(last.error);
        if(last.revision)http("archive",{revision:last.revision,record:{run_id:status.run_id,...last}}).catch(error=>message("运行结果已生效，但记录归档失败："+error.message));
      }
      refresh();
    }catch(error){message(error.message);}
    setTimeout(poll,initial.limits.poll_ms);
  }
  root.dataset.ready="true";poll();
}
