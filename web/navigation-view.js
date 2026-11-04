// Public task geometry and discrete progress only; this layer never reads robot truth.
export class WaypointOverlay{
  constructor(profile){
    const level=profile.campaign?.levels.find(item=>item.level_id===profile.campaign.active_level);
    this.route=level?.allowed_layers?.includes("waypoints")?level.navigation:null;
    this.style=level?.visualization?.waypoints;this.runId=null;this.state=null;
  }
  update(runId,state){
    if(runId!==this.runId){this.state=null;this.runId=runId;}
    const n=this.route?.points_m.length??0;
    this.state=state&&Number.isInteger(state.goal_index)&&state.goal_index>=0&&state.goal_index<n
      &&Number.isInteger(state.reached_count)&&state.reached_count>=0&&state.reached_count<=n?{...state}:null;
  }
  points(){
    return (this.route?.points_m??[]).map((position,index)=>({position,index,
      status:this.state?.goal_index===index&&!this.state.complete?"current":index<(this.state?.reached_count??0)?"reached":"pending"}));
  }
}

export function drawWaypoints(ctx,point,panel,scale){
  const overlay=panel.navigation;
  if(!panel.enabled("waypoints")||!overlay.route||!overlay.style)return;
  const route=overlay.route,style=overlay.style,points=overlay.points();
  ctx.save();ctx.lineWidth=style.line_width_px;ctx.strokeStyle=style.route_color;
  const path=[...(route.initial_xy_m?[route.initial_xy_m]:[]),...route.points_m];
  ctx.beginPath();path.forEach((position,index)=>{const p=point(...position);if(index)ctx.lineTo(...p);else ctx.moveTo(...p);});ctx.stroke();
  ctx.font=`${style.font_size_px}px monospace`;
  for(const item of points){
    const [x,y]=point(...item.position),color=style[`${item.status}_color`];
    if(item.status==="current"){
      ctx.fillStyle=style.tolerance_color;ctx.strokeStyle=color;ctx.beginPath();
      ctx.arc(x,y,route.position_tolerance_m*scale,0,2*Math.PI);ctx.fill();ctx.stroke();
    }
    ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,style.marker_radius_px,0,2*Math.PI);ctx.fill();
    ctx.fillText(String(item.index+1),x+2*style.marker_radius_px,y-style.marker_radius_px);
  }
  ctx.restore();
}
