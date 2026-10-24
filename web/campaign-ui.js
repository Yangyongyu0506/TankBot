// Teaching UI consumes the same narrow Authority controls in both runtime profiles.
import {bindingHint} from "/keyboard.js";
export async function mountCampaign(profile,browser,onState,releaseControls){
  const $=id=>document.getElementById(id),levels=profile.campaign?.levels??[];
  if(!levels.length){$("tab-task").hidden=true;return;}
  const current=levels.find(level=>level.level_id===profile.campaign.active_level);
  $("level-select").replaceChildren(...levels.map(level=>{
    const option=document.createElement("option");option.value=level.level_id;option.textContent=level.title;
    option.selected=level===current;return option;
  }));
  $("task-title").textContent=current?.title??"选择教学关卡";
  $("task-problem").textContent=current?.problem??"C0–C2 依次学习驾驶、坐标变换与噪声跟踪。";
  function updateHints(){$("task-hints").replaceChildren(...(current?.hints??[]).map(text=>{const li=document.createElement("li");li.textContent=bindingHint(text);return li;}));}
  updateHints();window.addEventListener("bindings-changed",updateHints);
  $("finish-level").disabled=!current;
  if(current){
    document.querySelector("h1").textContent=current.title;
    $("tab-task").click();
    $("state-heading").textContent="02 / AUTHORIZED SELF POSE";
    $("legend-pose").textContent="系统自定位";
    $("view-note").textContent=current.level_id==="c0"?"C0 真值练习：车体、靶标与弹道均获授权显示。":"系统只提供自身位姿；敌车位置来自 Python 的估计。雷达图仅显示车体系观测。";
    $("mode-label").textContent=current.level_id==="c0"?"C0 · 真值练习":"教学视图 · 系统自定位 / 玩家目标估计";
  }
  const initial=await (await fetch("/api/workspace")).json(),token=initial.control_token;
  async function updateProgress(){
    const response=await fetch("/api/progress"),progress=await response.json();
    if(!response.ok)throw Error(progress.error??"读取存档失败");
    for(const option of $("level-select").options){
      const level=levels.find(item=>item.level_id===option.value),completed=progress.completed_levels.includes(option.value);
      option.disabled=!progress.developer_mode&&!progress.unlocked_levels.includes(option.value);
      option.textContent=level.title+(option.disabled?" · 未解锁":completed?" · 已通关":"");
    }
  }
  await updateProgress();
  async function runtime(path,value={}){
    const r=browser?await browser.post(path,value):await fetch(path,path==="/api/campaign"?undefined:{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":token},body:JSON.stringify(value)});
    const result=await r.json();if(!r.ok)throw Error(result.error??"关卡请求失败");return result;
  }
  $("start-level").onclick=async()=>{
    const workspace=$("workspace-panel");
    if(workspace.dataset.dirty==="true"||workspace.dataset.busy==="true"||workspace.dataset.runtimeBusy==="true"){
      $("task-message").textContent="请先保存草稿，并等待当前测试或部署结束。";return;
    }
    $("start-level").disabled=true;releaseControls();
    try{
      const r=await fetch("/api/campaign/start",{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":token},body:JSON.stringify({level_id:$("level-select").value})});
      const result=await r.json();if(!r.ok)throw Error(result.error??"关卡启动失败");
      window.location.reload();
    }catch(error){$("task-message").textContent=error.message;$("start-level").disabled=false;}
  };
  $("finish-level").onclick=async()=>{
    try{releaseControls();await runtime("/api/campaign/finish");await poll();}
    catch(error){$("task-message").textContent=error.message;}
  };
  let timer;
  async function poll(){
    try{
      const {attempt,save_error}=await runtime("/api/campaign");
      if(browser?.saveError()){await browser.retrySave();}
      await updateProgress();
      onState(attempt);
      $("task-status").textContent=attempt?({active:"进行中",passed:"已通关",ended:"本次尝试已结束"}[attempt.status]):"自由试验场";
      $("task-status").dataset.status=attempt?.status??"sandbox";
      $("finish-level").disabled=!attempt||attempt.status!=="active";
      if(attempt){
        const p=attempt.progress;
        $("task-progress").textContent=attempt.level_id==="c2"?`敌车 HP：${attempt.enemy_hp} / ${attempt.enemy_max_hp}`:
          attempt.level_id==="c0"?`移动 ≥ ${current.objective.movement_m} m ${p.moved?"✓":"○"}　转向 ≥ ${current.objective.turn_rad} rad ${p.turned?"✓":"○"}　命中 ${p.hit?"✓":"○"}`:
          `目标估计 ${p.has_estimate?"✓":"○"}　命中 ${p.hit?"✓":"○"}`;
        if(attempt.result){
          const r=attempt.result;
          $("task-message").textContent=(r.passed?"通关！可选择下一关，已有源码会保留。":"可修改代码，再点击开始 / 重试。")+
            (r.rmse_m==null?"":" 本次估计 RMSE："+r.rmse_m.toFixed(3)+" m（仅结束后公布）。");
          if(save_error||browser?.saveError())$("task-message").textContent=save_error||browser.saveError();
        }
      }
    }catch(error){$("task-message").textContent=error.message;}
    clearTimeout(timer);timer=setTimeout(poll,profile.view.poll_ms*15);
  }
  await poll();
}

export function drawRadar(canvas,message,range){
  const ctx=canvas.getContext("2d"),cx=canvas.width/2,cy=canvas.height/2,r=Math.min(cx,cy)-18;
  ctx.clearRect(0,0,canvas.width,canvas.height);ctx.strokeStyle="#355548";ctx.fillStyle="#a9c5b6";
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();
  ctx.font="10px monospace";ctx.fillText("+x ↑  +y ←",8,12);ctx.fillText(`${range} m`,cx+r-24,canvas.height-3);
  ctx.fillStyle="#f4cf7e";
  for(const hit of message?.payload.detections??[]){
    const distance=hit.range_m/range*r;
    ctx.beginPath();ctx.arc(cx-Math.sin(hit.bearing_rad)*distance,cy-Math.cos(hit.bearing_rad)*distance,3,0,Math.PI*2);ctx.fill();
  }
}
