const $ = id => document.getElementById(id);
const canvas = $("arena"), ctx = canvas.getContext("2d");
let profile, snapshot, previous, current, received = 0, trail = [], keys = new Set();
let controlBusy = false;
let controlQueued = false;
const normalize = a => Math.atan2(Math.sin(a), Math.cos(a));
const point = (x,y) => [canvas.width/2 + x*canvas.width/14, canvas.height/2-y*canvas.width/14];

async function command() {
  if (!profile) return;
  if (controlBusy) {controlQueued = true;return;}
  controlBusy = true;
  const axis = (a,b) => Number(keys.has(a))-Number(keys.has(b));
  const omni = profile.chassis === "omnidirectional";
  const twist = {linear:{x:axis("KeyW","KeyS")*profile.view.keyboard_linear_mps,y:omni?axis("KeyA","KeyD")*profile.view.keyboard_linear_mps:0,z:0},angular:{x:0,y:0,z:(omni?axis("KeyQ","KeyE"):axis("KeyA","KeyD"))*profile.view.keyboard_yaw_radps}};
  try {
    const response = await fetch("/api/cmd_vel", {method:"POST",headers:{"Content-Type":"application/json","X-TankBot-Control":profile.control_token},body:JSON.stringify(twist)});
    if (!response.ok) $("connection").textContent = "控制指令被拒绝";
  } catch { $("connection").textContent = "连接中断"; }
  finally { controlBusy=false;if(controlQueued){controlQueued=false;command();} }
}
function key(code, down) {
  if (!["KeyW","KeyA","KeyS","KeyD","KeyQ","KeyE"].includes(code)) return;
  if (down) keys.add(code); else keys.delete(code);
  document.querySelectorAll(`[data-key="${code}"]`).forEach(e=>e.classList.toggle("active",down));
  command();
}
window.addEventListener("keydown", e=>{if (!e.repeat && !["INPUT","TEXTAREA"].includes(e.target.tagName)){key(e.code,true);if(keys.has(e.code))e.preventDefault();}});
window.addEventListener("keyup", e=>key(e.code,false));
window.addEventListener("blur", ()=>{keys.clear();document.querySelectorAll(".active").forEach(e=>e.classList.remove("active"));command();});
document.querySelectorAll("button[data-key]").forEach(button=>{
  button.addEventListener("pointerdown",e=>{button.setPointerCapture(e.pointerId);key(button.dataset.key,true);});
  for(const event of ["pointerup","pointercancel"])button.addEventListener(event,()=>key(button.dataset.key,false));
});

async function poll() {
  try {
    const r=await fetch("/api/view");if(!r.ok)throw Error("view");
    const message=await r.json();
    if(message.run_id!==profile.run_id){location.reload();return;}
    if(snapshot && (snapshot.sequence_number>=message.sequence_number || snapshot.payload.view_revision>message.payload.view_revision))return;
    const last=snapshot?.payload.selected_pose;
    if(snapshot && (snapshot.payload.view_revision!==message.payload.view_revision || last?.source_id!==message.payload.selected_pose?.source_id || last?.frame_id!==message.payload.selected_pose?.frame_id)){previous=current=null;trail=[];}
    snapshot=message;
    const s=message.payload.selected_pose;
    if(s){
      previous=current;current={...s.pose,stale:s.freshness==="stale"};received=performance.now();
      if(previous && Math.hypot(current.x_m-previous.x_m,current.y_m-previous.y_m)>profile.view.interpolation_jump_m){previous=current;trail=[];}
      if(!trail.length||trail.at(-1).tick!==s.simulation_tick)trail.push({...current,tick:s.simulation_tick});
      trail=trail.slice(-profile.view.max_visual_trail);
      for(const [id,value]of [["x",s.pose.x_m],["y",s.pose.y_m],["yaw",s.pose.yaw_rad]])$(id).textContent=value.toFixed(3);
      $("tick").textContent=s.simulation_tick;$("pose-label").textContent=`${s.source_id} / ${s.frame_id} · ${s.freshness}`;
      $("freshness").textContent=s.freshness==="fresh"?"已授权的算法估计 · 显示保留估计误差":"估计过期，暂留位置；超龄后隐藏";
    }else{
      current=previous=null;trail=[];for(const id of ["x","y","yaw","tick"])$(id).textContent="—";
      $("pose-label").textContent="等待合法位姿估计";
    }
    for(const m of message.payload.local_observations){
      if(m.schema==="joint_state@1"){
        $("wheels").replaceChildren(...m.payload.name.map((name,i)=>{const row=document.createElement("div"),label=document.createElement("span"),value=document.createElement("strong");label.textContent=name;value.textContent=`${m.payload.velocity[i].toFixed(2)} rad/s`;row.append(label,value);return row;}));
      }
      if(m.schema==="imu@1"){
        $("gyro").textContent=`${m.payload.angular_velocity_z_radps.toFixed(3)} rad/s`;
        $("accel").textContent=`aₓ ${m.payload.linear_acceleration_x_mps2.toFixed(2)} · aᵧ ${m.payload.linear_acceleration_y_mps2.toFixed(2)} m/s²`;
      }
    }
    $("connection").textContent="● 本地仿真在线";
  } catch {current=previous=null;$("connection").textContent="连接中断";}
}
function draw(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.strokeStyle="#1e3432";ctx.lineWidth=1;
  for(let i=-7;i<=7;i++){const [x]=point(i,0);ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,canvas.height);ctx.stroke();}
  for(let i=-5;i<=5;i++){const [,y]=point(0,i);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();}
  ctx.fillStyle="#8ba69a";ctx.font="12px monospace";ctx.fillText("x →",canvas.width-50,canvas.height/2-12);ctx.fillText("y ↑",canvas.width/2+12,30);
  const scale=canvas.width/14;
  if(profile){
    for(const wall of profile.walls){const [x,y]=point(...wall.center);ctx.fillStyle="#30453f";ctx.strokeStyle="#50675b";ctx.fillRect(x-wall.size[0]*scale/2,y-wall.size[1]*scale/2,wall.size[0]*scale,wall.size[1]*scale);ctx.strokeRect(x-wall.size[0]*scale/2,y-wall.size[1]*scale/2,wall.size[0]*scale,wall.size[1]*scale);}
    if(current){
      ctx.strokeStyle="#4a97756b";ctx.lineWidth=2;ctx.beginPath();trail.forEach((p,i)=>{const[x,y]=point(p.x_m,p.y_m);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
      const a=previous||current,t=Math.min(1,(performance.now()-received)/profile.view.poll_ms);
      const x=a.x_m+(current.x_m-a.x_m)*t,y=a.y_m+(current.y_m-a.y_m)*t,angle=a.yaw_rad+normalize(current.yaw_rad-a.yaw_rad)*t;
      const p=point(x,y);ctx.save();ctx.translate(...p);ctx.rotate(-angle);ctx.fillStyle=current.stale?"#ba9a50":"#8fe3b5";ctx.shadowColor="#8fe3b566";ctx.shadowBlur=15;
      const l=profile.body.length_m*scale,w=profile.body.width_m*scale;
      ctx.beginPath();ctx.roundRect(-l/2,-w/2,l,w,profile.body.corner_radius_m*scale);ctx.fill();ctx.shadowBlur=0;
      ctx.fillStyle="#1f4c3c";ctx.fillRect(-l*.35,-w*.5,l*.7,w*.15);ctx.fillRect(-l*.35,w*.35,l*.7,w*.15);
      ctx.beginPath();ctx.moveTo(l*.28,0);ctx.lineTo(-l*.08,-w*.18);ctx.lineTo(-l*.08,w*.18);ctx.closePath();ctx.fill();ctx.restore();
    }
  }
  requestAnimationFrame(draw);
}
try {
  const response=await fetch("/api/profile");if(!response.ok)throw Error("profile");profile=await response.json();
  const omni=profile.chassis==="omnidirectional";
  $("physics-rate").textContent=`${profile.physics_hz} Hz SIMULATION`;
  for(const key of ["KeyQ","KeyE"])document.querySelector(`[data-key="${key}"]`).hidden=!omni;
  $("chassis").textContent=omni?"四轮麦克纳姆 / X45°":"差速底盘 / Differential";
  $("controls").textContent=omni?"W/S 前后 · A/D 横移 · Q/E 转向":"W/S 前后 · A/D 转向";
  await poll();setInterval(poll,profile.view.poll_ms);setInterval(()=>{if(keys.size)command();},profile.view.keyboard_refresh_ms);
}catch{$("connection").textContent="无法连接本地 Host";}
draw();
