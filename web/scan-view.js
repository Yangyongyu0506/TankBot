// Authorized current scan + exact sample-tick player pose. No world geometry.
export class ScanHistory {
  constructor(profile){
    const level=profile.campaign?.levels.find(l=>l.level_id===profile.campaign.active_level);
    this.style=level?.visualization?.scan_view;
    this.allowed=new Set(level?.allowed_layers??[]);
    this.identity=null;this.poses=new Map();this.scans=new Map();this.scan=null;this.tick=0;this.source=null;
  }
  update(view){
    if(!this.style)return;
    const p=view.payload,source=p.selected_pose?.source_id;
    const identity=JSON.stringify([view.run_id,p.view_revision,source,p.selected_pose?.frame_id]);
    if(identity!==this.identity){this.poses.clear();this.scans.clear();this.scan=null;this.identity=identity;}
    this.tick=view.simulation_tick;this.source=source;
    for(const pose of p.pose_estimates??[]){
      if(source==='system'||pose.frame_id!=='map'||pose.payload.child_frame_id!=='base_link'
         ||pose.channel!==`/robot/estimates/${source}/pose`||pose.run_id!==view.run_id)continue;
      if(pose.simulation_tick<=this.tick)this.poses.set(pose.simulation_tick,pose.payload);
    }
    for(const [tick] of this.poses)if(this.tick-tick>this.style.history_ticks)this.poses.delete(tick);
    while(this.poses.size>this.style.history_samples)this.poses.delete(this.poses.keys().next().value);
    const scan=(p.local_observations??[]).find(m=>m.schema==='scan2d@1');
    if(scan&&(scan.frame_id!=='base_link'||scan.payload.sample_tick!==scan.simulation_tick))this.scans.clear();
    this.scan=scan&&scan.run_id===view.run_id&&scan.frame_id==='base_link'
      &&scan.payload.sample_tick===scan.simulation_tick&&scan.simulation_tick<=this.tick
      &&this.tick-scan.simulation_tick<=this.style.fresh_ticks?scan:null;
    if(this.scan)this.scans.set(this.scan.simulation_tick,this.scan);
    for(const [tick] of this.scans)if(this.tick-tick>this.style.fresh_ticks)this.scans.delete(tick);
    while(this.scans.size>this.style.history_samples)this.scans.delete(this.scans.keys().next().value);
  }
  bodyPoints(){
    if(!this.scan||!this.allowed.has('scan'))return [];
    const p=this.scan.payload;
    return p.ranges_m.flatMap((r,i)=>p.hit_mask[i]?[[r*Math.cos(p.angle_min_rad+i*p.angle_increment_rad),r*Math.sin(p.angle_min_rad+i*p.angle_increment_rad)]]:[]);
  }
  mapPoints(){
    if(!this.allowed.has('scan_points'))return [];
    // A pose can arrive one commit later than its scan. Keep only bounded pending
    // frames and show the latest exact match, never an accumulated map.
    const ticks=[...this.scans.keys()].filter(t=>this.poses.has(t)).sort((a,b)=>b-a);
    if(!ticks.length)return [];
    const scan=this.scans.get(ticks[0]),pose=this.poses.get(ticks[0]),p=scan.payload;
    this.projectedTick=ticks[0];
    const c=Math.cos(pose.yaw_rad),s=Math.sin(pose.yaw_rad);
    return p.ranges_m.flatMap((r,i)=>{
      if(!p.hit_mask[i])return [];
      const a=p.angle_min_rad+i*p.angle_increment_rad,x=r*Math.cos(a),y=r*Math.sin(a);
      return [[pose.x_m+c*x-s*y,pose.y_m+s*x+c*y]];
    });
  }
}

export function drawScan(ctx,point,panel){
  if(!panel.enabled('scan_points'))return;
  ctx.save();ctx.fillStyle=panel.scans.style?.point_color;
  for(const xy of panel.scans.mapPoints()){
    ctx.beginPath();ctx.arc(...point(...xy),panel.scans.style.point_radius_px,0,2*Math.PI);ctx.fill();
  }
  ctx.restore();
}

export function drawScanPanel(canvas,history){
  const ctx=canvas.getContext('2d'),size=history.style?.panel_size_px??canvas.width;
  canvas.width=size;canvas.height=size;ctx.clearRect(0,0,size,size);
  if(!history.scan)return;
  const scale=size/(2*history.scan.payload.range_max_m),center=size/2;
  ctx.strokeStyle=history.style.ray_color;ctx.beginPath();ctx.moveTo(center,center);ctx.lineTo(center,8);ctx.stroke();
  ctx.fillStyle=history.style.point_color;
  for(const [x,y] of history.bodyPoints()){ctx.beginPath();ctx.arc(center-y*scale,center-x*scale,history.style.point_radius_px,0,2*Math.PI);ctx.fill();}
}
