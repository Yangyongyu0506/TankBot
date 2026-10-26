// Workspace changes are explicit revisions; renderer and input controls do not own player code.
import {mountLearning} from "/learning-ui.js";
import {sourceLocation} from "/runtime-logs.js";
import {renderFileTree,revealSelectedFile} from "/file-tree.js";
export {setupWorkspaceDialog} from "/workspace-dialog.js";

export async function mountWorkspace(browser){
  const $=id=>document.getElementById(id),root=$("workspace-panel");
  let snapshot,files,selected,editor,plan,status,busy=false,token,level,learning,needsUpgrade=false,editorDefaultFile=null,pendingDeploymentId=null,editFiles=[];
  const message=text=>{$("workspace-message").textContent=text;};
  const showLogs=source=>window.dispatchEvent(new CustomEvent("tankbot-show-runtime-logs",{detail:{source}}));
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
    const ended=Boolean(status?.attempt_status&&status.attempt_status!=="active");
    root.dataset.busy=String(busy);
    root.dataset.dirty=String(dirty());
    root.dataset.runtimeBusy=String(Boolean(status?.job));
    root.dataset.revision=snapshot.revision;
    $("workspace-revision").textContent=(dirty()?"未保存 · ":"已保存 · ")+snapshot.revision.slice(0,12);
    renderFileTree($("file-list"),files,{selected,editFiles,dirtyPaths:Object.keys(files).filter(path=>files[path]!==snapshot.files[path]),onOpen:open});
    $("save-workspace").disabled=busy||!dirty();
    $("test-workspace").disabled=ended||busy||Boolean(status?.job);
    const ready=status?.reports.some(r=>r.revision===snapshot.revision&&r.status==="Ready");
    $("deploy-workspace").disabled=ended||needsUpgrade||busy||dirty()||Boolean(status?.job)||!ready;
    const deployHelp=ended?"本次关卡已结束；可以修改并保存代码，重试关卡后再测试和部署。":needsUpgrade?"尚未测试算法：请先预览并更新课程运行框架。":
      busy?"正在处理当前操作，请稍候。":status?.job?"正在测试或准备运行版本，完成后会更新部署状态。":
      dirty()?"代码有未保存的修改；保存并重新测试后才能部署。":ready?"当前快照测试通过，可以部署。":
      status?.last?.status==="Failed"&&status.last.revision===snapshot.revision?"当前快照测试失败；请查看下方错误，修改后重新测试。":"当前快照尚未测试通过；通过后部署按钮会亮起。";
    $("deploy-help").textContent=deployHelp;$("deploy-workspace").title=deployHelp;
    $("workspace-upgrade").hidden=!needsUpgrade;
    $("preview-teaching-upgrade").disabled=busy||Boolean(status?.job);
    $("rollback-workspace").disabled=ended||busy||Boolean(status?.job)||!$("deployment-history").value;
  }
  function open(path){selected=path;$("editor-path").textContent=path;editor.open(path,files[path]);learning?.file(path);refresh();revealSelectedFile($("file-list"));}
  function accept(value){snapshot=value;files={...value.files};const preferred=editorDefaultFile;open(files[selected]!==undefined?selected:(preferred&&preferred in files?preferred:Object.keys(files).find(p=>p.endsWith("odometry.py"))||Object.keys(files)[0]));}
  async function save(){
    const changes={};for(const p of new Set([...Object.keys(files),...Object.keys(snapshot.files)]))if(files[p]!==snapshot.files[p])changes[p]=files[p]??null;
    if(Object.keys(changes).length)accept(await http("save",{revision:snapshot.revision,changes}));
    message("已保存。当前运行版本保持原样。");
  }
  async function action(fn){if(busy)return;busy=true;refresh();try{await fn();}catch(error){
    if(level&&error.message.startsWith("TEACHING_TEMPLATE_UPGRADE_REQUIRED")){
      try{await previewUpgrade();}catch(next){message(next.message);}
    }else{message(error.message);locate(error.message);}
  }finally{busy=false;refresh();}}
  function locate(text){const location=sourceLocation(text);if(location&&files[location.path]!==undefined){open(location.path);editor.go(location.line);}}
  function showPlan(value){
    plan=value;$("migration-panel").hidden=false;$("migration-list").replaceChildren();
    const guided=plan.purpose==="teaching-framework-upgrade";
    $("migration-explanation").textContent=guided?(plan.message?plan.message+" ":"")+"本次只替换下列课程运行文件，并补齐缺失文件。perception/ 等已有算法文件不参与替换；运行文件中自己的修改可从旧版本恢复。确认预览后，可更新框架并继续测试。":"已有文件默认保留；请逐项检查后应用。";
    $("upgrade-and-test").hidden=!guided;$("apply-migration").hidden=guided;$("select-framework-upgrade").hidden=guided;
    for(const entry of plan.entries){
      const detail=document.createElement("details"),summary=document.createElement("summary");summary.textContent=entry.path+" · "+(entry.action==="create"?"新增":guided?"运行文件：确认后更新":"已有文件：默认保留");detail.append(summary);
      const row=document.createElement("div");row.className="migration-columns";
      for(const [label,text] of [["旧模板",entry.base],["当前内容",entry.current],["新建议",entry.incoming]]){
        const column=document.createElement("div"),heading=document.createElement("strong"),pre=document.createElement("pre");heading.textContent=label;pre.textContent=text??"（无）";column.append(heading,pre);row.append(column);
      }
      detail.append(row);
      if(entry.action==="conflict"&&!guided){
        const select=document.createElement("select");select.dataset.path=entry.path;
        for(const [value,label] of [["keep","保留当前文件"],["incoming","明确采用新建议（旧 revision 仍保留）"]]){const option=document.createElement("option");option.value=value;option.textContent=label;select.append(option);}detail.append(select);
      }
      $("migration-list").append(detail);
    }
    message(guided?"草稿已保存。课程运行框架需要更新，尚未测试算法；请检查预览，再点击“保留算法，更新框架并继续测试”。":plan.already_applied?"此模板已应用；再次预览不会覆盖文件。":"请检查新增文件与冲突，再应用。可先在编辑器手动合并后重新预览。");
  }
  async function refreshUpgrade(){
    const current=await (await fetch("/api/workspace")).json();
    if(current.snapshot.revision!==snapshot.revision)throw Error("其他窗口更新了工作区；请先导出当前草稿，再刷新以读取新版本。");
    needsUpgrade=current.learning.upgrade_required;learning.updateUpgrade(needsUpgrade);refresh();return needsUpgrade;
  }
  async function previewUpgrade(){await save();showPlan(await http("upgrade",{revision:snapshot.revision}));}
  async function testSnapshot(){
    await save();
    if(await refreshUpgrade()){await previewUpgrade();return;}
    showLogs("test");
    status=await runtime("test",{revision:snapshot.revision,snapshot});message("正在独立运行环境中测试此快照…");
  }
  const initial=await (await fetch("/api/workspace")).json();token=initial.control_token;level=initial.level_id;editorDefaultFile=initial.learning.lesson.ui?.default_file;snapshot=initial.snapshot;files={...snapshot.files};
  $("workspace-dialog").addEventListener("toggle",()=>{if($("workspace-dialog").open)revealSelectedFile($("file-list"));});
  editFiles=initial.learning.lesson.edit_files??initial.learning.lesson.functions.map(fn=>fn.path);
  $("test-workspace").title=initial.learning.testing.checks.join("\n")+"\n"+initial.learning.testing.meaning;
  const {createEditor}=await import("/editor-bundle.js");
  editor=createEditor($("code-editor"),(path,text)=>{files[path]=text;refresh();},()=>action(save),initial.learning);
  window.addEventListener("tankbot-open-source",event=>{
    const {path,line,revision}=event.detail;
    if(files[path]===undefined)return;
    if(!$("workspace-dialog").open)$("open-workspace").click();
    if(!$("workspace-dialog").open)return;
    if(!$("learning-pane").hidden)$("close-learning").click();
    open(path);editor.go(line);
    if(dirty()||(revision&&revision!==snapshot.revision))message("日志来自已部署/测试的快照；当前源码已有变化，行号可能不同，可按历史 revision 预览原代码。");
  });
  needsUpgrade=initial.learning.upgrade_required;
  learning=mountLearning(initial.learning,open,()=>action(previewUpgrade));
  accept(snapshot);
  $("save-workspace").onclick=()=>action(save);
  $("test-workspace").onclick=()=>action(testSnapshot);
  $("preview-teaching-upgrade").onclick=()=>action(previewUpgrade);
  $("deploy-workspace").onclick=()=>action(async()=>{
    status=await runtime("deploy",{revision:snapshot.revision,snapshot});
    pendingDeploymentId=status.job?.id;
    message("正在启动候选版本，成功后自动返回游戏…");
  });
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
    accept(await http("apply",{plan_id:plan.plan_id,revision:plan.base_revision,resolutions}));await refreshUpgrade();$("migration-panel").hidden=true;message("已创建新 revision；之前的 revision 可导出或恢复。");
  });
  $("upgrade-and-test").onclick=()=>action(async()=>{
    const resolutions=Object.fromEntries(plan.entries.map(entry=>[entry.path,"incoming"]));
    accept(await http("apply",{plan_id:plan.plan_id,revision:plan.base_revision,resolutions}));
    await refreshUpgrade();$("migration-panel").hidden=true;await testSnapshot();
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
  let previousLast="",previousFault="";
  async function poll(){
    try{
      status=await runtime("");root.dataset.deployment=JSON.stringify(status);root.dataset.revision=snapshot.revision;
      window.dispatchEvent(new CustomEvent("tankbot-deployment-status",{detail:status}));
      $("active-deployment").textContent=status.active?status.active.sha256.slice(0,12)+" · tick "+status.active.activated_tick:"启动示例（尚未部署工作区）";
      $("deployment-state").textContent=status.attempt_status&&status.attempt_status!=="active"?"关卡已结束":status.job?(status.job.kind+" / "+status.job.phase):status.runtime_fault?"程序已停止 · "+(status.runtime_diagnostic?.summary??status.runtime_fault):status.last?.status||"Editing";
      const faultKey=status.runtime_fault?JSON.stringify([status.active?.deployment_id,status.runtime_fault]):"";
      if(faultKey&&faultKey!==previousFault)showLogs("runtime");
      previousFault=faultKey;
      const history=$("deployment-history"),choice=history.value;
      history.replaceChildren(...[...new Map(status.history.map(d=>[d.sha256,d])).values()].map(d=>{const o=document.createElement("option");o.value=d.sha256;o.textContent=d.sha256.slice(0,12)+" · "+d.revision.slice(0,8);return o;}));
      if([...history.options].some(o=>o.value===choice))history.value=choice;
      if(status.last&&JSON.stringify(status.last)!==previousLast){previousLast=JSON.stringify(status.last);
        const last=status.last;
        const diagnostic=last.diagnostic,location=diagnostic?.path?`${diagnostic.path}:${diagnostic.line}: `:"";
        message(last.status==="Failed"?`${last.kind==="test"?"测试":"启动"}失败：${location}${diagnostic?.summary??last.error}。完整输出见下方日志。`:last.status==="Ready"?`测试通过：${last.unit_tests} 个单元测试，${last.simulation_batches} 个传感器仿真批次；摘要 ${last.sha256.slice(0,12)}`:`已激活 ${last.sha256.slice(0,12)}；物理世界继续运行。`);
        if(last.status==="Failed"){showLogs(last.kind);locate(location||last.error);}
        else if(last.status==="Active")showLogs("all");
        if(last.revision)http("archive",{revision:last.revision,record:{run_id:status.run_id,...last}}).catch(error=>message("运行结果已生效，但记录归档失败："+error.message));
      }
      // Campaign visibility belongs to its attempt gate; sandbox deployments close on acknowledgement.
      if(pendingDeploymentId&&status.last?.id===pendingDeploymentId){
        pendingDeploymentId=null;
        if(status.last.status==="Active"&&!status.attempt_status)$("workspace-dialog").close();
      }
      refresh();
    }catch(error){message(error.message);}
    setTimeout(poll,initial.limits.poll_ms);
  }
  root.dataset.ready="true";poll();
}
