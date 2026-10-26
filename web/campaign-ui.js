// Teaching UI consumes the same narrow Authority controls in both runtime profiles.
import {bindingHint} from "/keyboard.js";
import {mountLiveMetric} from "/live-metrics.js";
export function attemptSummary(attempt){
  if(!attempt)return "";
  const clock=attempt.timing,remaining=Math.ceil(clock.remaining_s),minutes=Math.floor(remaining/60),seconds=String(remaining%60).padStart(2,"0");
  const time=attempt.phase==="preparing"?`尚未计时 · 限时 ${clock.time_limit_s} 秒`:`剩余 ${minutes}:${seconds}`;
  const health=attempt.player_hp==null?"":` · 我方 HP ${attempt.player_hp}/${attempt.player_max_hp} · 敌方 HP ${attempt.enemy_hp}/${attempt.enemy_max_hp}`;
  const reasons={aborted:"已主动结束",timeout:"失败：超时",player_dead:"失败：玩家死亡",objective_completed:"已通关"};
  return (attempt.result?reasons[attempt.result.reason]??"本次尝试已结束":time)+health;
}
export async function mountCampaign(profile,browser,onState,releaseControls){
  const $=id=>document.getElementById(id),levels=profile.campaign?.levels??[],chapters=profile.campaign?.chapters??[];
  if(!levels.length){$("tab-task").hidden=true;return;}
  const current=levels.find(level=>level.level_id===profile.campaign.active_level);
  const liveMetric=mountLiveMetric($("live-evaluation"),current?.live_feedback);
  const options=levels.map(level=>{
    const option=document.createElement("option");option.value=level.level_id;option.textContent=level.title;
    option.selected=level===current;return option;
  });
  $("level-select").replaceChildren();
  if(chapters.length){for(const chapter of chapters){const group=document.createElement("optgroup");group.label=chapter.title;for(const level of levels)if(level.chapter_id===chapter.chapter_id)group.append(options[levels.indexOf(level)]);if(group.children.length)$("level-select").append(group);}}
  else $("level-select").append(...options);
  const chapter=chapters.find(item=>item.chapter_id===current?.chapter_id);
  $("task-chapter").textContent=chapter?chapter.title:"CAMPAIGN";
  $("task-title").textContent=current?.title??"选择教学关卡";
  $("task-problem").textContent=current?.problem??"Hello Robot → Weapons → Locomotion";
  function updateHints(){$("task-hints").replaceChildren(...(current?.hints??[]).map(text=>{const li=document.createElement("li");li.textContent=bindingHint(text);return li;}));}
  updateHints();window.addEventListener("bindings-changed",updateHints);
  $("finish-level").disabled=!current;
  if(current){
    document.querySelector("h1").textContent=current.title;
    $("tab-task").click();
    $("state-heading").textContent=current.ui.state_heading;
    $("legend-pose").textContent=current.ui.legend_pose;
    $("view-note").textContent=current.ui.view_note;
    $("mode-label").textContent=current.ui.mode_label;
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
  const finish=async()=>{
    try{releaseControls();await runtime("/api/campaign/finish");await poll();}
    catch(error){$("task-message").textContent=error.message;}
  };
  $("finish-level").onclick=finish;
  $("editor-finish-level").onclick=finish;
  let timer;
  async function poll(){
    try{
      const {run_id,attempt,save_error}=await runtime("/api/campaign");
      liveMetric.update(run_id,attempt);
      if(browser?.saveError()){await browser.retrySave();}
      await updateProgress();
      onState(attempt);
      $("task-status").textContent=attempt?(attempt.phase==="preparing"?"准备中 · 尚未开始计时":{active:"进行中",passed:"已通关",ended:"本次尝试已结束"}[attempt.status]):"自由试验场";
      $("task-status").dataset.status=attempt?.status??"sandbox";
      $("finish-level").disabled=!attempt||attempt.status!=="active";
      $("editor-finish-level").disabled=$("finish-level").disabled;
      $("editor-attempt").hidden=!attempt;
      $("campaign-summary").hidden=!attempt;
      $("campaign-summary").textContent=attemptSummary(attempt);
      $("campaign-summary").dataset.phase=attempt?.phase??"";
      $("editor-attempt-status").textContent=attemptSummary(attempt)+(attempt?.status!=="active"?" · 请重试关卡后再测试/部署。":attempt.phase==="preparing"?" · 测试不计时；部署成功后返回游戏，本局结束前锁定编辑器。":" · 正在计时；请先结束本次尝试，再编辑代码。");
      if(liveMetric.summary)$("editor-attempt-status").textContent+=" · "+liveMetric.summary;
      if(attempt){
        const p=attempt.progress;
        $("task-progress").textContent=attempt.player_hp!=null?`我方 HP：${attempt.player_hp} / ${attempt.player_max_hp}　敌车 HP：${attempt.enemy_hp} / ${attempt.enemy_max_hp}`:
          current.ui.progress_layout==="movement"?`移动 ≥ ${current.objective.movement_m} m ${p.moved?"✓":"○"}　转向 ≥ ${current.objective.turn_rad} rad ${p.turned?"✓":"○"}　命中 ${p.hit?"✓":"○"}`:
          `目标估计 ${p.has_estimate?"✓":"○"}　命中 ${p.hit?"✓":"○"}`;
        if(attempt.result){
          const r=attempt.result;
          $("task-message").textContent=(r.passed?"通关！可选择下一关，已有源码会保留。":attemptSummary(attempt)+"。可修改代码，再点击开始 / 重试。")+
            (r.rmse_m==null?"":" 本次估计 RMSE："+r.rmse_m.toFixed(3)+(current.live_feedback?" m。":" m（仅结束后公布）。"));
          if(save_error||browser?.saveError())$("task-message").textContent=save_error||browser.saveError();
        }else{
          $("task-message").textContent=attempt.phase==="preparing"?(attempt.timing.start_on==="first_control"?"首次有效驾驶、炮台或开火操作后计时。":"保存 → 测试 → 部署。首次成功部署前不计时；部署后按本关权限运行机器人。"):"本局运行中，代码编辑器已锁定。发现问题请点击“结束本次尝试”，或点击“开始 / 重试”重置关卡；源码会保留。";
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
