import {SceneTimeline, FollowCamera, drawChassis, drawTurret} from "/rendering.js";
import {mountWorkspace, setupWorkspaceDialog} from "/workspace-ui.js";
import {connectBrowser} from "/browser-client.js";
import {mountCampaign, drawRadar} from "/campaign-ui.js";
import {GamepadDriver, neutralControls, moving, manualTargets} from "/gamepad.js";
import {mountSettings} from "/settings-ui.js";
import {binding,controlKey,keyLabel} from "/keyboard.js";
import {mountVisualization,drawVisualization} from "/visualization.js";

const $ = id => document.getElementById(id);
const canvas = $("arena"), ctx = canvas.getContext("2d");
let profile, snapshot, timeline, camera, trail = [], keys = new Set(), online = false;
let frames = 0, statsSince = 0, renderFps = 0;
let controlBusy = false;
let controlQueued = false;
let browser;
let settings,visualization;
let campaignEnded = false;
let joy,joyControls=neutralControls(),lastControlAt=-Infinity,lastManualActive=false,lastJoyList="";
const point = (x, y) => camera.project(x, y, canvas.width, canvas.height, profile.rendering.viewport_width_m);

async function command() {
  if (!profile || campaignEnded) return;
  if (controlBusy) {controlQueued = true;return;}
  controlBusy = true;
  const targets=manualTargets(profile,keys,joyControls,canDrive());
  lastControlAt=performance.now();lastManualActive=targets.active;
  try {
    const requests=[];
    if(profile.control_sources.chassis==="keyboard")requests.push(post("/api/cmd_vel",targets.twist));
    if(profile.control_sources.turret==="keyboard")requests.push(post("/api/turret_cmd_vel",targets.turret));
    if((await Promise.all(requests)).some(response=>!response.ok))$("connection").textContent="控制指令被拒绝";
  } catch { $("connection").textContent = "连接中断"; }
  finally { controlBusy=false;if(controlQueued){controlQueued=false;command();} }
}
function post(path,value){
  if(browser)return browser.post(path,value);
  return fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":profile.control_token},body:JSON.stringify(value)});
}
async function fire(){
  if(!profile||!canDrive()||profile.control_sources.weapon!=="keyboard")return;
  try{
    const response=await post("/api/fire",{request_id:crypto.randomUUID()});
    const result=await response.json();
    $("weapon").textContent=response.ok?`发射请求：${result.status}`:"开火请求被拒绝";
  }catch{$("connection").textContent="连接中断";}
}
$("fire").addEventListener("click",fire);
function key(code, down) {
  if(down&&$("workspace-dialog").open)return;
  if(code==="Space"){if(down)fire();return;}
  if (!["KeyW","KeyA","KeyS","KeyD","KeyQ","KeyE","KeyJ","KeyL"].includes(code)) return;
  if (down) keys.add(code); else keys.delete(code);
  document.querySelectorAll(`[data-key="${code}"]`).forEach(e=>e.classList.toggle("active",down));
  command();
}
function releaseControls(){keys.clear();joy?.suspend();joyControls=neutralControls();document.querySelectorAll("button[data-key].active").forEach(e=>e.classList.remove("active"));command();}
setupWorkspaceDialog(releaseControls);
const editing = target => $("settings-dialog").open||$("workspace-dialog").open||target?.closest?.("input, textarea, select, [contenteditable]");
const visibleFocused=()=>!document.hidden&&document.hasFocus();
const canDrive=()=>visibleFocused()&&!campaignEnded&&!editing(document.activeElement);
function updateControlLabels(){
  if(!profile)return;
  const omni=profile.chassis==="omnidirectional",k=action=>keyLabel(binding(action));
  $("controls").textContent=`${k("forward")}/${k("backward")} 前后 · ${k("left")}/${k("right")} ${omni?"横移":"转向"}`+(omni?` · ${k("turn_left")}/${k("turn_right")} 转向`:"");
  $("weapon-control").textContent=profile.control_sources.turret==="keyboard"?`${k("turret_left")}/${k("turret_right")} 旋转炮台 · ${k("fire")} 单发`:"机器人控制炮台与武器";
}
window.addEventListener("bindings-changed",updateControlLabels);
window.addEventListener("keydown", e=>{
  if(e.code==="Space"&&e.target?.closest?.("button, a"))return;
  const mapped=controlKey(e.code);
  if (!e.repeat&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!e.shiftKey&&!e.isComposing&&!editing(e.target)&&mapped){key(mapped,true);e.preventDefault();}
});
window.addEventListener("keyup", e=>{const mapped=controlKey(e.code);if(mapped&&keys.has(mapped))key(mapped,false);});
window.addEventListener("focusin", e=>{if(editing(e.target))releaseControls();});
window.addEventListener("blur",()=>{joy?.suspend(true);releaseControls();});
document.addEventListener("visibilitychange",()=>{if(document.hidden){joy?.suspend(true);releaseControls();}});
window.addEventListener("gamepaddisconnected",()=>{joy?.suspend(true);releaseControls();});
window.addEventListener("gamepadconnected",()=>joy?.suspend(true));

function sampleGamepad(now){
  if(!joy)return;
  let frame,error="";
  try{
    if(joy.enabled&&typeof navigator.getGamepads!=="function")throw Error("浏览器不支持手柄 API");
    frame=joy.sample(joy.enabled?navigator.getGamepads():[],{motionAllowed:canDrive(),uiAllowed:visibleFocused()&&!$("settings-dialog").open});
  }catch{
    joy.suspend(true);frame={...neutralControls(),devices:[],device:null,status:"unavailable"};
    error=isSecureContext?"浏览器未开放手柄访问；请检查浏览器设置。":"手柄需要 HTTPS 或 localhost；请使用安全地址。";
  }
  const previous=joyControls;joyControls=frame;
  const list=JSON.stringify([frame.devices.map(p=>[p.index,p.id,p.mapping]),joy.preferred]);
  if(list!==lastJoyList){
    lastJoyList=list;
    const auto=document.createElement("option");auto.value="auto";auto.textContent="自动选择手柄";
    $("gamepad-select").replaceChildren(auto,...frame.devices.map(p=>{
      const option=document.createElement("option");option.value=p.index;option.textContent=`${p.index+1} · ${p.id}${p.mapping==="standard"?"":"（自定义映射）"}`;return option;
    }));
    if(joy.preferred!==null&&!frame.devices.some(p=>p.index===joy.preferred)){
      const missing=document.createElement("option");missing.value=joy.preferred;missing.textContent=`手柄 ${joy.preferred+1} · 已断开`;$("gamepad-select").append(missing);
    }
    $("gamepad-select").value=joy.preferred??"auto";
  }
  const status={waiting:"连接手柄后按任意键，再松开摇杆和按键。",disabled:"手柄已停用，可继续用键盘。",
    unsupported:"映射不匹配；请切到标准手柄模式，或在配置中设置自定义轴/按键。",
    neutral:"请松开摇杆、肩键和扳机，回中后接管。",paused:"操控暂停；返回游戏后先松开摇杆与按键。",
    ready:"手柄就绪 · RT 单发 · Start 打开 / 收起编辑器",unavailable:error}[frame.status];
  const label=(frame.device?frame.device.id+" · ":"")+status;
  if($("gamepad-status").textContent!==label)$("gamepad-status").textContent=label;
  $("gamepad-status").dataset.status=frame.status;
  const indicator=frame.status==="ready"?"手柄：已连接":frame.status==="neutral"?"手柄：请回中":frame.status==="paused"?"手柄：暂停":frame.status==="unsupported"?"手柄：映射待配置":frame.status==="disabled"?"手柄：已停用":"手柄：未连接";
  if($("gamepad-indicator").textContent!==indicator)$("gamepad-indicator").textContent=indicator;
  if(frame.editor){$("open-workspace").click();joy.suspend();joyControls=neutralControls();command();return;}
  if(frame.fire)fire();
  if(moving(previous)&&!moving(frame))command();
  const period=moving(frame)?joy.config.refresh_ms:profile.view.keyboard_refresh_ms;
  if((keys.size||moving(frame)||lastManualActive)&&now-lastControlAt>=period)command();
}
const hudTabs=[...document.querySelectorAll(".hud-tabs [role=tab]")];
function selectHud(tab){
  for(const item of hudTabs){
    const selected=item===tab;item.setAttribute("aria-selected",String(selected));item.tabIndex=selected?0:-1;
    $(item.getAttribute("aria-controls")).hidden=!selected;
  }
}
for(const [index,tab] of hudTabs.entries()){
  tab.addEventListener("click",()=>selectHud(tab));
  tab.addEventListener("keydown",event=>{
    if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
    event.preventDefault();
    const next=event.key==="Home"?0:event.key==="End"?hudTabs.length-1:(index+(event.key==="ArrowRight"?1:-1)+hudTabs.length)%hudTabs.length;
    selectHud(hudTabs[next]);hudTabs[next].focus();
  });
}
document.querySelectorAll("button[data-key]").forEach(button=>{
  button.addEventListener("pointerdown",e=>{button.setPointerCapture(e.pointerId);key(button.dataset.key,true);});
  for(const event of ["pointerup","pointercancel"])button.addEventListener(event,()=>key(button.dataset.key,false));
});

async function poll() {
  const started = performance.now();
  try {
    const message = browser ? await browser.view() : await (async()=>{const r=await fetch("/api/view");if(!r.ok)throw Error("view");return r.json();})();
    if (message.run_id !== profile.run_id) { location.reload(); return; }
    online = true;
    $("connection").textContent = browser ? "● 浏览器 WASM / Pyodide 在线" : "● 本地仿真在线";
    if(browser){
      const health=browser.health();
      canvas.dataset.runtimeTick=health?.tick??"";
      canvas.dataset.runtimeFault=health?.runtime_fault??"";
      canvas.dataset.poseCommits=health?.pose_commits??0;
      canvas.dataset.runtimeHealth=JSON.stringify(health??{});
      if(health?.runtime_fault)$("connection").textContent="● 仿真在线 · Python 已停止，可测试并重新部署";
    }
    const result = timeline.push(message, performance.now());
    let developerData=null;
    if(visualization.developer){
      const response=browser?await browser.post("/api/developer",{}):await fetch("/api/developer");
      if(response.ok)developerData=await response.json();
    }
    visualization.update(message,developerData,performance.now());
    if (result.accepted) {
      if (result.reset || result.poseJump) trail = [];
      if (result.clearCamera) camera.reset();
      snapshot = message;
      const selected = message.payload.selected_pose;
      if (selected) {
        if (!trail.length || trail.at(-1).tick !== selected.simulation_tick) trail.push({...selected.pose, tick: selected.simulation_tick});
        trail = trail.slice(-profile.view.max_visual_trail);
        for (const [id, value] of [["x", selected.pose.x_m], ["y", selected.pose.y_m], ["yaw", selected.pose.yaw_rad]]) $(id).textContent = value.toFixed(3);
        $("tick").textContent = selected.simulation_tick;
        $("pose-label").textContent = `${selected.source_id} / ${selected.frame_id} · ${selected.freshness}`;
        $("freshness").textContent = profile.view_mode === "campaign" ? "系统提供自身位姿；敌车只有玩家目标估计" : profile.view_mode === "weapons-practice" ? "显式真值练习视图 · Python 仍只接收传感器" : selected.freshness === "fresh" ? "相机跟随估计 x/y · 世界坐标方向固定" : "估计过期，暂留位置；超龄后隐藏";
      } else {
        trail = [];
        for (const id of ["x", "y", "yaw", "tick"]) $(id).textContent = "—";
        $("pose-label").textContent = "等待合法位姿估计 · 相机保持";
      }
      for (const m of message.payload.local_observations) {
        if(m.schema==="radar@1"){
          drawRadar($("radar-canvas"),m,profile.radar_calibration.range_m);
          $("radar-status").textContent=`tick ${m.simulation_tick} · ${m.payload.detections.length} 回波（车体系）`;
        }
        if (m.schema === "joint_state@1" && m.channel === "/robot/sensors/joint_states") {
          $("wheels").replaceChildren(...m.payload.name.map((name, i) => {
            const row = document.createElement("div"), label = document.createElement("span"), value = document.createElement("strong");
            label.textContent = name; value.textContent = `${m.payload.velocity[i].toFixed(2)} rad/s`;
            row.append(label, value); return row;
          }));
        }
        if (m.channel === "/robot/turret/joint_states") $("turret").textContent = `q ${m.payload.position[0].toFixed(2)} rad · ω ${m.payload.velocity[0].toFixed(2)} rad/s`;
        if (m.schema === "weapon_state@1") {
          const w = m.payload;
          $("weapon").textContent = `${w.ready ? "就绪" : `冷却 ${w.cooldown_remaining_ticks} ticks`} · 发射 ${w.shots_fired} · 受击 ${w.hits_received} · ${w.last_result?.status || "—"}`;
        }
        if (m.schema === "imu@1") {
          $("gyro").textContent = `${m.payload.angular_velocity_z_radps.toFixed(3)} rad/s`;
          $("accel").textContent = `aₓ ${m.payload.linear_acceleration_x_mps2.toFixed(2)} · aᵧ ${m.payload.linear_acceleration_y_mps2.toFixed(2)} m/s²`;
        }
      }
    }
  } catch { online = false; $("connection").textContent = "连接中断"; }
  // One request at a time; polling frequency is independent of RAF and physics.
  setTimeout(poll, Math.max(0, profile.view.poll_ms - (performance.now() - started)));
}

function draw(now) {
  sampleGamepad(now);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (profile) {
    const frame = online ? timeline.sample(now) : {pose: null, objects: [], turretAngle: 0};
    const debugFrame=online?visualization?.sample(now):null;
    camera.follow(visualization?.enabled("truth_robot")&&debugFrame?.pose?debugFrame.pose:frame.pose);
    const scale = canvas.width / profile.rendering.viewport_width_m;
    const halfX = canvas.width / scale / 2, halfY = canvas.height / scale / 2;
    const grid = profile.rendering.grid_spacing_m;
    ctx.strokeStyle = "#1e3432"; ctx.lineWidth = 1;
    for (let x = Math.floor((camera.x - halfX) / grid) * grid; x <= camera.x + halfX; x += grid) {
      const [sx] = point(x, 0); ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, canvas.height); ctx.stroke();
    }
    for (let y = Math.floor((camera.y - halfY) / grid) * grid; y <= camera.y + halfY; y += grid) {
      const [, sy] = point(0, y); ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(canvas.width, sy); ctx.stroke();
    }
    for (const wall of visualization?.enabled("map")?profile.walls:[]) {
      const [x, y] = point(...wall.center);
      ctx.fillStyle = "#30453f"; ctx.strokeStyle = "#50675b";
      ctx.fillRect(x - wall.size[0] * scale / 2, y - wall.size[1] * scale / 2, wall.size[0] * scale, wall.size[1] * scale);
      ctx.strokeRect(x - wall.size[0] * scale / 2, y - wall.size[1] * scale / 2, wall.size[0] * scale, wall.size[1] * scale);
    }
    const objects=debugFrame?.objects??frame.objects;
    for (const object of objects) {
      if (object.kind === "projectile") {
        if(!visualization?.enabled("projectiles"))continue;
        ctx.fillStyle = "#ffd47a"; ctx.beginPath(); ctx.arc(...point(object.x_m, object.y_m), object.radius_m * scale, 0, Math.PI * 2); ctx.fill();
      } else if (object.kind === "target") {
        if(!visualization?.enabled("truth_targets"))continue;
        ctx.save(); ctx.translate(...point(object.pose.x_m, object.pose.y_m)); ctx.rotate(-object.pose.yaw_rad);
        const l = profile.body.length_m * scale, w = profile.body.width_m * scale;
        ctx.fillStyle = "#af6972"; ctx.beginPath(); ctx.roundRect(-l / 2, -w / 2, l, w, profile.body.corner_radius_m * scale); ctx.fill();
        ctx.fillStyle = "#fff0de"; ctx.fillText(String(object.hits), -4, 4); ctx.restore();
      }
    }
    if (frame.pose&&visualization?.enabled("trail")) {
      ctx.strokeStyle = "#4a97756b"; ctx.lineWidth = 2; ctx.beginPath();
      // Future samples are in the interpolation buffer, not on the visible trail yet.
      let count = 0;
      for (const p of trail) {
        if (p.tick * 1000 / profile.physics_hz > frame.simulationTimeMs) break;
        const [x, y] = point(p.x_m, p.y_m); count++ ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      if (count) ctx.lineTo(...point(frame.pose.x_m, frame.pose.y_m));
      ctx.stroke();
    }
    const bodies=[...(frame.pose&&visualization?.enabled("robot")?[{pose:frame.pose,angle:frame.turretAngle,truth:false}]:[]),
      ...(debugFrame?.pose&&visualization?.enabled("truth_robot")?[{pose:debugFrame.pose,angle:debugFrame.turretAngle,truth:true}]:[])];
    for(const body of bodies){
      ctx.save(); ctx.translate(...point(body.pose.x_m, body.pose.y_m)); ctx.rotate(-body.pose.yaw_rad);
      if(body.truth)ctx.globalAlpha=.7;
      drawChassis(ctx, profile.chassis_visual, scale, body.pose.stale, profile.wheel_calibration);
      if(visualization?.enabled("turret"))drawTurret(ctx, profile.chassis_visual, scale, body.angle, profile.turret_muzzle_offset_m, profile.rendering.barrel_width_m);
      if(body.truth){ctx.strokeStyle="#61d7f0";ctx.lineWidth=2;ctx.strokeRect(-profile.body.length_m*scale/2,-profile.body.width_m*scale/2,profile.body.length_m*scale,profile.body.width_m*scale);}
      ctx.restore();
    }
    if(frame.targetEstimate&&visualization?.enabled("target_estimates")){
      const p=frame.targetEstimate,[x,y]=point(p.x_m,p.y_m);
      ctx.strokeStyle="#f4cf7e";ctx.fillStyle="#f4cf7e";ctx.lineWidth=2;ctx.setLineDash([5,4]);
      ctx.beginPath();ctx.arc(x,y,profile.body.width_m*scale/2,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);
      ctx.beginPath();ctx.moveTo(x-7,y);ctx.lineTo(x+7,y);ctx.moveTo(x,y-7);ctx.lineTo(x,y+7);ctx.stroke();
      ctx.font="12px sans-serif";ctx.fillText("目标估计",x+12,y-12);
    }
    if(visualization)drawVisualization(ctx,point,frame,debugFrame,visualization,profile,scale);
    ctx.fillStyle = "#8ba69a"; ctx.font = "12px monospace";
    ctx.fillText("WORLD  +x →  +y ↑", canvas.width - 170, 28);
    // These diagnostics contain only the displayed, already-authorized state.
    canvas.dataset.cameraX = camera.x; canvas.dataset.cameraY = camera.y; canvas.dataset.cameraYaw = 0;
    canvas.dataset.model = profile.chassis_visual.model_id;
    canvas.dataset.chassis = profile.chassis;
    canvas.dataset.renderTimeMs = frame.simulationTimeMs ?? "";
    canvas.dataset.robotVisible = bodies.length>0;
    canvas.dataset.developerMode=Boolean(visualization?.developer);
    canvas.dataset.visibleLayers=JSON.stringify(Object.keys(settings.value.layers).filter(key=>visualization.enabled(key)));
    canvas.dataset.truthObjects=debugFrame?.objects.length??0;
    canvas.dataset.robotScreenX = frame.pose ? point(frame.pose.x_m, frame.pose.y_m)[0] : "";
    canvas.dataset.robotScreenY = frame.pose ? point(frame.pose.x_m, frame.pose.y_m)[1] : "";
    canvas.dataset.robotYaw = frame.pose?.yaw_rad ?? "";
    canvas.dataset.viewSequence = snapshot?.sequence_number ?? "";
    const firstProjectile = frame.objects.find(o => o.kind === "projectile");
    canvas.dataset.projectileX = firstProjectile?.x_m ?? "";
    canvas.dataset.projectileY = firstProjectile?.y_m ?? "";
    canvas.dataset.targetEstimateX=frame.targetEstimate?.x_m??"";
    canvas.dataset.targetEstimateY=frame.targetEstimate?.y_m??"";
    frames++;
    if (now - statsSince >= profile.rendering.stats_interval_ms) {
      renderFps = Math.round(frames * 1000 / (now - statsSince)); frames = 0; statsSince = now;
      $("physics-rate").textContent = `${profile.physics_hz} Hz SIM · ${profile.view.snapshot_hz} Hz VIEW · ${renderFps} FPS`;
    }
  }
  requestAnimationFrame(draw);
}

try {
  settings=await mountSettings(releaseControls,()=>browser?.close());
  if(new URLSearchParams(location.search).get("runtime")==="browser"){
    $("connection").textContent="正在加载浏览器运行环境…";
    browser=await connectBrowser();profile=browser.profile;
  }else{
    const response = await fetch("/api/profile"); if (!response.ok) throw Error("profile"); profile = await response.json();
  }
  timeline = new SceneTimeline(profile.physics_hz, profile.rendering, profile.view.interpolation_jump_m);
  camera = new FollowCamera(profile.rendering.camera_origin_m);
  visualization=mountVisualization(profile,settings);
  statsSince = performance.now();
  const omni = profile.chassis === "omnidirectional";
  joy=new GamepadDriver(profile.view.gamepad,profile.chassis);
  $("gamepad-enabled").checked=joy.enabled;
  $("gamepad-enabled").disabled=!profile.view.gamepad;
  $("gamepad-enabled").onchange=()=>{releaseControls();joy.setEnabled($("gamepad-enabled").checked);$("arena").focus();};
  $("gamepad-select").onchange=()=>{releaseControls();joy.select($("gamepad-select").value==="auto"?null:Number($("gamepad-select").value));$("arena").focus();};
  $("gamepad-indicator").onclick=()=>selectHud($("tab-chassis"));
  $("gamepad-mapping").textContent=omni?"左摇杆：前后 / 横移；LB/RB：车体左 / 右转；右摇杆横轴：炮台；RT：单发；Start：编辑器。":"左摇杆：前后 / 车体转向；LB/RB 也可转向；右摇杆横轴：炮台；RT：单发；Start：编辑器。";
  for (const key of ["KeyQ", "KeyE"]) document.querySelector(`[data-key="${key}"]`).hidden = !omni;
  $("chassis").textContent = omni ? "四全向轮 / X-drive · 90°" : "差速底盘 / Differential";
  updateControlLabels();
  if (profile.view_mode === "weapons-practice") {
    $("state-heading").textContent = "02 / AUTHORIZED GROUND TRUTH";
    $("legend-pose").textContent = "获授权真值";
    $("view-note").textContent = "真值练习显示真实车体、弹丸与靶标。Python 仍只接收授权传感器，不能读取这些世界状态。";
  }
  $("mode-label").textContent = profile.view_mode === "weapons-practice" ? "真值练习视图 / Ground Truth · 跟随平移，世界方向固定" : "估计视图 / Estimated State · 相机跟随授权估计";
  $("fire").disabled = profile.control_sources.weapon !== "keyboard";
  mountWorkspace(browser).catch(error=>$("workspace-message").textContent="编辑器加载失败："+error.message+"。请运行 python3 tools/build.py 后刷新页面。");
  mountCampaign(profile,browser,state=>{
    const ended=Boolean(state&&state.status!=="active");
    if(ended&&!campaignEnded){campaignEnded=true;releaseControls();}
    $("fire").disabled=ended||profile.control_sources.weapon!=="keyboard";
  },releaseControls).then(()=>{
    if(visualization.developer){
      $("mode-label").textContent="开发者可视化 · 真值、估计与传感器图层可独立开关";
      $("view-note").textContent="图层面板可自由显示真值、估计和观测；Python 的输入仍按关卡授权。开发者练习不会解锁玩家关卡。";
    }
  }).catch(error=>$("task-message").textContent=error.message);
  poll();
} catch(error) { $("connection").textContent = `启动失败：${error.message}`; }
requestAnimationFrame(draw);
