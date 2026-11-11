// Public static geometry and Authority-validated player output; no robot truth.
export class PlanningOverlay {
  constructor(profile){
    const level=profile.campaign?.levels.find(item=>item.level_id===profile.campaign.active_level);
    this.allowed=new Set(level?.allowed_layers??[]);
    this.task=level?.global_planning??null;
    this.style=level?.visualization?.global_planning;
    this.runId=null;this.route=null;
  }
  update(runId,state){
    if(runId!==this.runId){this.route=null;this.runId=runId;}
    this.route=this.task&&state?.task_id===this.task.task_id&&state.route?.task_id===this.task.task_id
      &&this.allowed.has('path')?state.route:null;
  }
}

export function drawPlanning(ctx,point,panel){
  const overlay=panel.globalPlanning,task=overlay?.task,style=overlay?.style;
  if(!task||!style)return;
  ctx.save();
  function grid(data,color){
    if(!data||!task.map)return;
    const [ox,oy]=task.map.origin_xy,r=task.map.resolution_m;
    ctx.fillStyle=color;ctx.globalAlpha=style.grid_alpha;
    for(let row=0;row<data.length;row++)for(let col=0;col<data[row].length;col++){
      if(!data[row][col])continue;
      const a=point(ox+col*r,oy+row*r),b=point(ox+(col+1)*r,oy+(row+1)*r);
      ctx.fillRect(Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(b[0]-a[0]),Math.abs(b[1]-a[1]));
    }
    ctx.globalAlpha=1;
  }
  if(panel.enabled('safety_grid')&&overlay.allowed.has('safety_grid'))grid(task.inflated_grid,style.inflated_color);
  if(panel.enabled('planning_map')&&overlay.allowed.has('planning_map')){
    grid(task.map?.grid,style.raw_color);
    ctx.font=`${style.font_size_px}px monospace`;
    for(const [position,label,color] of [[task.start_xy,'公开起点',style.start_color],[task.goal_xy,'公开终点',style.goal_color]]){
      const [x,y]=point(...position);ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,style.marker_radius_px,0,2*Math.PI);ctx.fill();
      ctx.fillText(label,x+style.marker_radius_px*2,y-style.marker_radius_px);
    }
  }
  if(panel.enabled('path')&&overlay.allowed.has('path')&&overlay.route){
    ctx.strokeStyle=style.route_color;ctx.lineWidth=style.line_width_px;ctx.beginPath();
    overlay.route.points_m.forEach((xy,index)=>{const p=point(...xy);if(index)ctx.lineTo(...p);else ctx.moveTo(...p);});ctx.stroke();
  }
  ctx.restore();
}
