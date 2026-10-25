// Displays Authority-admitted contracts and explicitly authorized robot topics.
export function mountRobotGraph(profile,browser){
  const $=id=>document.getElementById(id);
  let token;
  fetch("/api/workspace").then(r=>r.json()).then(value=>{token=value.control_token;});
  $("pose-provider").onchange=async()=>{
    try{
      const path="/api/pose_source",value={module_id:$("pose-provider").value};
      const response=browser?await browser.post(path,value):await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":token},body:JSON.stringify(value)});
      const result=await response.json();if(!response.ok)throw Error(result.error??"切换失败");
      $("graph-message").textContent="位姿来源已切换；历史显示缓存已清除。";
    }catch(error){$("graph-message").textContent=error.message;}
  };
  window.addEventListener("tankbot-deployment-status",({detail:status})=>{
    const graph=status.graph;
    $("robot-graph-list").replaceChildren();
    $("pose-provider-control").hidden=!graph?.pose_selection_allowed;
    if(!graph){$("graph-summary").textContent="本关使用单模块包装。Weapons 的 C3 起解锁多模块，已有算法文件继续复用。";return;}
    $("graph-summary").textContent=`${graph.modules.length} 个模块 · 固定 tick 提交${status.runtime_fault?" · Runtime 已停止："+status.runtime_fault:""}`;
    for(const module of graph.modules){
      const row=document.createElement("section"),heading=document.createElement("strong"),schedule=document.createElement("p"),ports=document.createElement("p"),state=document.createElement("p");
      row.className="graph-module";heading.textContent=module.module_id;
      schedule.textContent=(module.execution.mode==="periodic"?`每 ${module.execution.period_ticks} tick`:`事件触发 · 最小间隔 ${module.execution.min_interval_ticks} tick`)+` · 预算 ${module.execution.budget_ms} ms`;
      ports.textContent=Object.entries(module.inputs).map(([port,channel])=>`${channel} → ${port}`).concat(Object.entries(module.outputs).map(([port,channel])=>`${port} → ${channel}`)).join("\n");
      state.textContent=module.fault?"已停止："+module.fault:`最近激活 tick ${module.last_activation_tick} · 连续错误 ${module.failures}`+((module.waiting_inputs?.length??0)?` · 等待输入：${module.waiting_inputs.join("、")}`:"");
      row.append(heading,schedule,ports,state);$("robot-graph-list").append(row);
    }
    const providers=graph.modules.filter(module=>Object.values(module.outputs).includes(`/robot/estimates/${module.module_id}/pose`));
    const select=$("pose-provider"),key=providers.map(m=>m.module_id).join(":");
    if(select.dataset.providers!==key){select.replaceChildren(...providers.map(module=>{const option=document.createElement("option");option.value=module.module_id;option.textContent=module.module_id;return option;}));select.dataset.providers=key;}
    select.value=graph.pose_source.module_id??"";
  });
}
