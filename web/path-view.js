// Static task reference and explicitly authorized discrete feedback. No robot truth.
export class PathOverlay {
  constructor(profile){
    const level=profile.campaign?.levels.find(item=>item.level_id===profile.campaign.active_level);
    this.allowed=new Set(level?.allowed_layers??[]);
    this.reference=level?.path_tracking??null;
    this.style=level?.visualization?.path_tracking;
    this.runId=null;this.state=null;
  }
  update(runId,state){
    if(runId!==this.runId){this.state=null;this.runId=runId;}
    const count=this.reference?.checkpoints_m?.length??0;
    this.state=state?.path_id===this.reference?.path_id&&Number.isInteger(state.reached_count)
      &&state.reached_count>=0&&state.reached_count<=count?{...state}:null;
  }
  points(){
    if(!this.allowed.has("checkpoints"))return [];
    return (this.reference?.checkpoints_m??[]).map((position,index)=>({position,index,
      status:index<(this.state?.reached_count??0)?"reached":index===(this.state?.reached_count??0)?"current":"pending"}));
  }
}

export function drawPath(ctx,point,panel,scale){
  const overlay=panel.pathTracking,reference=overlay?.reference,style=overlay?.style;
  if(!reference||!style)return;
  ctx.save();ctx.lineWidth=style.line_width_px;ctx.font=`${style.font_size_px}px monospace`;
  if(panel.enabled("path")&&overlay.allowed.has("path")&&reference.points_m){
    ctx.strokeStyle=style.route_color;ctx.beginPath();
    reference.points_m.forEach((position,index)=>{const p=point(...position);if(index)ctx.lineTo(...p);else ctx.moveTo(...p);});ctx.stroke();
    for(const [position,label,color] of [[reference.points_m[0],"起点",style.start_color],[reference.points_m.at(-1),"终点",style.end_color]]){
      const [x,y]=point(...position);ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,style.marker_radius_px,0,2*Math.PI);ctx.fill();
      ctx.fillText(label,x+style.marker_radius_px*2,y-style.marker_radius_px);
    }
  }
  if(panel.enabled("checkpoints")&&overlay.allowed.has("checkpoints")){
    for(const item of overlay.points()){
      const [x,y]=point(...item.position),color=style[`${item.status}_color`];
      if(item.status==="current"){
        ctx.fillStyle=style.tolerance_color;ctx.strokeStyle=color;ctx.beginPath();
        ctx.arc(x,y,reference.checkpoint_radius_m*scale,0,2*Math.PI);ctx.fill();ctx.stroke();
      }
      ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,style.marker_radius_px,0,2*Math.PI);ctx.fill();
      ctx.fillText(String(item.index+1),x+style.marker_radius_px*2,y+style.font_size_px);
    }
  }
  ctx.restore();
}
