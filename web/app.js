import {SceneTimeline, FollowCamera, drawChassis, drawTurret} from "/rendering.js";

const $ = id => document.getElementById(id);
const canvas = $("arena"), ctx = canvas.getContext("2d");
let profile, snapshot, timeline, camera, trail = [], keys = new Set(), online = false;
let frames = 0, statsSince = 0, renderFps = 0;
let controlBusy = false;
let controlQueued = false;
const point = (x, y) => camera.project(x, y, canvas.width, canvas.height, profile.rendering.viewport_width_m);

async function command() {
  if (!profile) return;
  if (controlBusy) {controlQueued = true;return;}
  controlBusy = true;
  const axis = (a,b) => Number(keys.has(a))-Number(keys.has(b));
  const omni = profile.chassis === "omnidirectional";
  const twist = {linear:{x:axis("KeyW","KeyS")*profile.view.keyboard_linear_mps,y:omni?axis("KeyA","KeyD")*profile.view.keyboard_linear_mps:0,z:0},angular:{x:0,y:0,z:(omni?axis("KeyQ","KeyE"):axis("KeyA","KeyD"))*profile.view.keyboard_yaw_radps}};
  try {
    const requests=[];
    if(profile.control_sources.chassis==="keyboard")requests.push(post("/api/cmd_vel",twist));
    if(profile.control_sources.turret==="keyboard")requests.push(post("/api/turret_cmd_vel",{velocity_radps:axis("KeyJ","KeyL")*profile.view.keyboard_turret_radps}));
    if((await Promise.all(requests)).some(response=>!response.ok))$("connection").textContent="控制指令被拒绝";
  } catch { $("connection").textContent = "连接中断"; }
  finally { controlBusy=false;if(controlQueued){controlQueued=false;command();} }
}
function post(path,value){
  return fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":profile.control_token},body:JSON.stringify(value)});
}
async function fire(){
  if(!profile||profile.control_sources.weapon!=="keyboard")return;
  try{
    const response=await post("/api/fire",{request_id:crypto.randomUUID()});
    const result=await response.json();
    $("weapon").textContent=response.ok?`发射请求：${result.status}`:"开火请求被拒绝";
  }catch{$("connection").textContent="连接中断";}
}
$("fire").addEventListener("click",fire);
function key(code, down) {
  if(code==="Space"){if(down)fire();return;}
  if (!["KeyW","KeyA","KeyS","KeyD","KeyQ","KeyE","KeyJ","KeyL"].includes(code)) return;
  if (down) keys.add(code); else keys.delete(code);
  document.querySelectorAll(`[data-key="${code}"]`).forEach(e=>e.classList.toggle("active",down));
  command();
}
window.addEventListener("keydown", e=>{if (!e.repeat && !["INPUT","TEXTAREA"].includes(e.target.tagName)){key(e.code,true);if(keys.has(e.code)||e.code==="Space")e.preventDefault();}});
window.addEventListener("keyup", e=>key(e.code,false));
window.addEventListener("blur", ()=>{keys.clear();document.querySelectorAll(".active").forEach(e=>e.classList.remove("active"));command();});
document.querySelectorAll("button[data-key]").forEach(button=>{
  button.addEventListener("pointerdown",e=>{button.setPointerCapture(e.pointerId);key(button.dataset.key,true);});
  for(const event of ["pointerup","pointercancel"])button.addEventListener(event,()=>key(button.dataset.key,false));
});

async function poll() {
  const started = performance.now();
  try {
    const r = await fetch("/api/view"); if (!r.ok) throw Error("view");
    const message = await r.json();
    if (message.run_id !== profile.run_id) { location.reload(); return; }
    online = true;
    $("connection").textContent = "● 本地仿真在线";
    const result = timeline.push(message, performance.now());
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
        $("freshness").textContent = profile.view_mode === "weapons-practice" ? "显式真值练习视图 · Python 仍只接收传感器" : selected.freshness === "fresh" ? "相机跟随估计 x/y · 世界坐标方向固定" : "估计过期，暂留位置；超龄后隐藏";
      } else {
        trail = [];
        for (const id of ["x", "y", "yaw", "tick"]) $(id).textContent = "—";
        $("pose-label").textContent = "等待合法位姿估计 · 相机保持";
      }
      for (const m of message.payload.local_observations) {
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
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (profile) {
    const frame = online ? timeline.sample(now) : {pose: null, objects: [], turretAngle: 0};
    camera.follow(frame.pose); // Exact same interpolated x/y as the robot; no second smoothing or yaw rotation.
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
    for (const wall of profile.walls) {
      const [x, y] = point(...wall.center);
      ctx.fillStyle = "#30453f"; ctx.strokeStyle = "#50675b";
      ctx.fillRect(x - wall.size[0] * scale / 2, y - wall.size[1] * scale / 2, wall.size[0] * scale, wall.size[1] * scale);
      ctx.strokeRect(x - wall.size[0] * scale / 2, y - wall.size[1] * scale / 2, wall.size[0] * scale, wall.size[1] * scale);
    }
    for (const object of frame.objects) {
      if (object.kind === "projectile") {
        ctx.fillStyle = "#ffd47a"; ctx.beginPath(); ctx.arc(...point(object.x_m, object.y_m), object.radius_m * scale, 0, Math.PI * 2); ctx.fill();
      } else if (object.kind === "target") {
        ctx.save(); ctx.translate(...point(object.pose.x_m, object.pose.y_m)); ctx.rotate(-object.pose.yaw_rad);
        const l = profile.body.length_m * scale, w = profile.body.width_m * scale;
        ctx.fillStyle = "#af6972"; ctx.beginPath(); ctx.roundRect(-l / 2, -w / 2, l, w, profile.body.corner_radius_m * scale); ctx.fill();
        ctx.fillStyle = "#fff0de"; ctx.fillText(String(object.hits), -4, 4); ctx.restore();
      }
    }
    if (frame.pose) {
      ctx.strokeStyle = "#4a97756b"; ctx.lineWidth = 2; ctx.beginPath();
      // Future samples are in the interpolation buffer, not on the visible trail yet.
      let count = 0;
      for (const p of trail) {
        if (p.tick * 1000 / profile.physics_hz > frame.simulationTimeMs) break;
        const [x, y] = point(p.x_m, p.y_m); count++ ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      if (count) ctx.lineTo(...point(frame.pose.x_m, frame.pose.y_m));
      ctx.stroke();
      ctx.save(); ctx.translate(...point(frame.pose.x_m, frame.pose.y_m)); ctx.rotate(-frame.pose.yaw_rad);
      drawChassis(ctx, profile.chassis_visual, scale, frame.pose.stale, profile.wheel_calibration);
      drawTurret(ctx, profile.chassis_visual, scale, frame.turretAngle, profile.turret_muzzle_offset_m, profile.rendering.barrel_width_m);
      ctx.restore();
    }
    ctx.fillStyle = "#8ba69a"; ctx.font = "12px monospace";
    ctx.fillText("WORLD  +x →  +y ↑", canvas.width - 170, 28);
    // These diagnostics contain only the displayed, already-authorized state.
    canvas.dataset.cameraX = camera.x; canvas.dataset.cameraY = camera.y; canvas.dataset.cameraYaw = 0;
    canvas.dataset.model = profile.chassis_visual.model_id;
    canvas.dataset.chassis = profile.chassis;
    canvas.dataset.renderTimeMs = frame.simulationTimeMs ?? "";
    canvas.dataset.robotVisible = Boolean(frame.pose);
    canvas.dataset.robotScreenX = frame.pose ? point(frame.pose.x_m, frame.pose.y_m)[0] : "";
    canvas.dataset.robotScreenY = frame.pose ? point(frame.pose.x_m, frame.pose.y_m)[1] : "";
    canvas.dataset.robotYaw = frame.pose?.yaw_rad ?? "";
    canvas.dataset.viewSequence = snapshot?.sequence_number ?? "";
    const firstProjectile = frame.objects.find(o => o.kind === "projectile");
    canvas.dataset.projectileX = firstProjectile?.x_m ?? "";
    canvas.dataset.projectileY = firstProjectile?.y_m ?? "";
    frames++;
    if (now - statsSince >= profile.rendering.stats_interval_ms) {
      renderFps = Math.round(frames * 1000 / (now - statsSince)); frames = 0; statsSince = now;
      $("physics-rate").textContent = `${profile.physics_hz} Hz SIM · ${profile.view.snapshot_hz} Hz VIEW · ${renderFps} FPS`;
    }
  }
  requestAnimationFrame(draw);
}

try {
  const response = await fetch("/api/profile"); if (!response.ok) throw Error("profile"); profile = await response.json();
  timeline = new SceneTimeline(profile.physics_hz, profile.rendering, profile.view.interpolation_jump_m);
  camera = new FollowCamera(profile.rendering.camera_origin_m);
  statsSince = performance.now();
  const omni = profile.chassis === "omnidirectional";
  for (const key of ["KeyQ", "KeyE"]) document.querySelector(`[data-key="${key}"]`).hidden = !omni;
  $("chassis").textContent = omni ? "四全向轮 / X-drive · 90°" : "差速底盘 / Differential";
  $("controls").textContent = omni ? "W/S 前后 · A/D 横移 · Q/E 转向" : "W/S 前后 · A/D 转向";
  if (profile.view_mode === "weapons-practice") {
    $("state-heading").textContent = "02 / AUTHORIZED GROUND TRUTH";
    $("legend-pose").textContent = "获授权真值";
    $("view-note").textContent = "真值练习显示真实车体、弹丸与靶标。Python 仍只接收授权传感器，不能读取这些世界状态。";
  }
  $("mode-label").textContent = profile.view_mode === "weapons-practice" ? "真值练习视图 / Ground Truth · 跟随平移，世界方向固定" : "估计视图 / Estimated State · 相机跟随授权估计";
  $("fire").disabled = profile.control_sources.weapon !== "keyboard";
  $("weapon-control").textContent = `炮台：${profile.control_sources.turret} · 武器：${profile.control_sources.weapon} · J/L 旋转，空格单发`;
  poll();
  setInterval(() => { if (keys.size) command(); }, profile.view.keyboard_refresh_ms);
} catch { $("connection").textContent = "无法连接本地 Host"; }
requestAnimationFrame(draw);
