import {SceneTimeline} from "./rendering.js";

export const layerLabels={map:"静态地图",robot:"本关授权车体位姿",trail:"授权位姿轨迹",target_estimates:"玩家目标估计",radar:"Radar 观测",imu:"IMU 数据 / 加速度箭头",encoders:"轮编码器数据",turret:"炮台与武器观测",truth_robot:"真实车体与炮台",truth_targets:"真实目标",projectiles:"真实弹丸",frames:"坐标系",velocities:"真实速度向量",colliders:"碰撞外形"};
export function allowedLayers(profile,developer){
  const current=profile.campaign?.levels.find(l=>l.level_id===profile.campaign.active_level),caps=current?.capabilities??[];
  if(current?.allowed_layers)return developer?Object.keys(layerLabels):current.allowed_layers;
  return Object.keys(layerLabels).filter(key=>{
    if(["truth_robot","velocities","colliders"].includes(key))return developer;
    if(key==="truth_targets")return developer||profile.view_mode==="weapons-practice"||caps.includes("view.enemy.truth");
    if(key==="projectiles")return developer||profile.view_mode==="weapons-practice"||caps.includes("view.projectiles.truth");
    if(key==="radar")return Boolean(profile.radar_calibration);
    return true;
  });
}

export function developerView(data,profile){
  const truth=data.truth,tick=data.simulation_tick,[x,y,yaw]=truth.truth_pose;
  return {run_id:data.run_id,sequence_number:tick,simulation_tick:tick,payload:{view_revision:0,
    selected_pose:truth.player_alive===false?null:{source_id:"system",frame_id:"map",simulation_tick:tick,freshness:"fresh",pose:{x_m:x,y_m:y,yaw_rad:yaw}},
    local_observations:Object.values(data.sensors),objects:[
      ...truth.projectiles.map(p=>({kind:"projectile",projectile_id:p.projectile_id,x_m:p.position[0],y_m:p.position[1],radius_m:p.radius_m??profile.projectile_radius_m})),
      ...truth.targets.filter(t=>t.alive).map(t=>({kind:"target",target_id:t.target_id,pose:{x_m:t.pose[0],y_m:t.pose[1],yaw_rad:t.pose[2]},hits:truth.target_hits[t.target_id]}))]}};
}

export function mountVisualization(profile,settings){
  const $=id=>document.getElementById(id),developer=settings.value.developer_mode,allowed=new Set(allowedLayers(profile,developer));
  const current=profile.campaign?.levels.find(level=>level.level_id===profile.campaign.active_level),configuration=current?.visualization;
  let layers=configuration&&!configuration.preserve_user_settings?Object.fromEntries(Object.keys(layerLabels).map(key=>[key,configuration.initial_enabled.includes(key)])):{...settings.value.layers},data=null,message=null,robotTopics=[],saveQueue=Promise.resolve();
  const history=new SceneTimeline(profile.physics_hz,profile.rendering,profile.view.interpolation_jump_m);
  $("visualization-note").textContent=developer?"开发者图层 · 可独立显示真值、估计和传感器；不会把真值发给玩家代码。":"只列出本关授权图层；显示来源仍由关卡权限决定。";
  $("layer-list").replaceChildren(...[...allowed].map(key=>{
    const label=document.createElement("label"),input=document.createElement("input");input.type="checkbox";input.checked=layers[key];input.dataset.layer=key;input.disabled=Boolean(configuration&&!configuration.user_toggleable.includes(key));
    input.onchange=()=>{
      if(input.disabled)return;
      layers[key]=input.checked;applyPanels();
      const candidate={...layers};
      saveQueue=saveQueue.catch(()=>{}).then(()=>settings.saveLayers(candidate)).then(()=>{$("layers-message").textContent="图层设置已保存。";}).catch(error=>{$("layers-message").textContent="保存失败："+error.message;});
    };
    label.append(input,document.createTextNode(layerLabels[key]));return label;
  }));
  function enabled(key){return allowed.has(key)&&layers[key];}
  function applyPanels(){
    $("wheels").hidden=!enabled("encoders");$("imu-panel").hidden=!enabled("imu");
    $("radar-panel").hidden=!enabled("radar");$("turret").hidden=!enabled("turret");$("weapon").hidden=!enabled("turret");
    $("hud-state").querySelector(".state-grid").hidden=!enabled("robot");$("freshness").hidden=!enabled("robot");
    $("pose-label").hidden=!enabled("robot");
  }
  function inspect(){
    const values={view:message};
    for(const item of message?.payload.local_observations??[])values[item.channel]=item;
    for(const item of message?.payload.target_estimates??[])values[item.channel]=item;
    for(const item of robotTopics)values[item.channel]=item;
    if(developer&&data){
      values["developer/truth"]=data.truth;values["developer/pose_candidates"]=data.pose_candidates;
      values["developer/selected_pose"]=data.selected_pose;values["developer/target_estimate"]=data.target_estimate;
      values["developer/runtime"]=data.runtime;values["developer/audit"]=data.audit;
      for(const [channel,item] of Object.entries(data.sensors))values[channel]=item;
    }
    const selected=$("message-topic").value,keys=Object.keys(values);
    if(JSON.stringify([...$("message-topic").options].map(o=>o.value))!==JSON.stringify(keys)){
      $("message-topic").replaceChildren(...keys.map(key=>{const option=document.createElement("option");option.value=key;option.textContent=key;return option;}));
      if(selected in values)$("message-topic").value=selected;
    }
    $("message-data").textContent=$("show-message").checked?JSON.stringify(values[$("message-topic").value],null,2):"消息内容已隐藏";
  }
  $("message-topic").onchange=inspect;$("show-message").onchange=inspect;
  window.addEventListener("tankbot-deployment-status",event=>{robotTopics=event.detail.graph?.topics??[];inspect();});
  applyPanels();
  return {enabled,developer,get data(){return data;},get message(){return message;},
    update(view,debug,now){message=view;data=developer?debug:null;if(data)history.push(developerView(data,profile),now);applyPanels();inspect();},
    sample:now=>data?history.sample(now):null};
}

export function drawVector(ctx,point,origin,vector,scale,color,label){
  const a=point(...origin),b=point(origin[0]+vector[0]*scale,origin[1]+vector[1]*scale),angle=Math.atan2(b[1]-a[1],b[0]-a[0]);
  ctx.save();ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);
  for(const turn of [-.5,.5]){ctx.moveTo(...b);ctx.lineTo(b[0]-9*Math.cos(angle+turn),b[1]-9*Math.sin(angle+turn));}ctx.stroke();
  ctx.font="11px monospace";ctx.fillText(label,b[0]+5,b[1]-5);ctx.restore();
}

export function drawVisualization(ctx,point,frame,debugFrame,panel,profile,scale){
  const base=panel.enabled("truth_robot")?debugFrame?.pose:frame.pose,data=panel.data;
  if(panel.enabled("frames")){
    const poses=[[0,0,0,"map"],...(base?[[base.x_m,base.y_m,base.yaw_rad,profile.radar_calibration?"base_link / radar_link":"base_link"]]:[])];
    for(const [x,y,yaw,name] of poses){
      drawVector(ctx,point,[x,y],[Math.cos(yaw),Math.sin(yaw)],.6,"#f59696",name+" +x");
      drawVector(ctx,point,[x,y],[-Math.sin(yaw),Math.cos(yaw)],.6,"#9cea9f","+y");
    }
  }
  const imu=panel.message?.payload.local_observations.find(m=>m.schema==="imu@1")?.payload;
  const radar=panel.message?.payload.local_observations.find(m=>m.schema==="radar@1")?.payload;
  if(panel.developer&&frame.pose&&panel.enabled("radar")&&radar){
    ctx.save();ctx.fillStyle="#d7a8ff";
    for(const hit of radar.detections){
      const angle=frame.pose.yaw_rad+hit.bearing_rad;
      ctx.beginPath();ctx.arc(...point(frame.pose.x_m+hit.range_m*Math.cos(angle),frame.pose.y_m+hit.range_m*Math.sin(angle)),3,0,Math.PI*2);ctx.fill();
    }
    ctx.restore();
  }
  if(base&&panel.enabled("imu")&&imu){
    const c=Math.cos(base.yaw_rad),s=Math.sin(base.yaw_rad),x=imu.linear_acceleration_x_mps2,y=imu.linear_acceleration_y_mps2;
    drawVector(ctx,point,[base.x_m,base.y_m],[c*x-s*y,s*x+c*y],.15,"#c3a5ff","IMU m/s² ×0.15");
  }
  if(panel.enabled("velocities")&&base&&data){
    const [vx,vy]=data.truth.truth_velocity,c=Math.cos(base.yaw_rad),s=Math.sin(base.yaw_rad);
    drawVector(ctx,point,[base.x_m,base.y_m],[c*vx-s*vy,s*vx+c*vy],.5,"#5fcef5","v m/s ×0.5");
    for(const t of data.truth.targets.filter(t=>t.alive))if(t.velocity){
      const c=Math.cos(t.pose[2]),s=Math.sin(t.pose[2]),[x,y]=t.velocity;
      drawVector(ctx,point,t.pose,[c*x-s*y,s*x+c*y],.5,"#5fcef5","v m/s ×0.5");
    }
  }
  if(panel.enabled("colliders")&&data){
    const poses=[...(data.truth.player_alive===false?[]:[data.truth.truth_pose]),...data.truth.targets.filter(t=>t.alive).map(t=>t.pose)];
    for(const [x,y,yaw] of poses){ctx.save();ctx.translate(...point(x,y));ctx.rotate(-yaw);ctx.strokeStyle="#ff9dd2";ctx.lineWidth=2;ctx.setLineDash([4,3]);ctx.beginPath();ctx.roundRect(-profile.body.length_m*scale/2,-profile.body.width_m*scale/2,profile.body.length_m*scale,profile.body.width_m*scale,profile.body.corner_radius_m*scale);ctx.stroke();ctx.restore();}
  }
}
