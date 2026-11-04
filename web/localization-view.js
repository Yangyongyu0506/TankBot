// Bounded presentation of already-authorized measurements and player estimates.
import {SceneTimeline} from "./rendering.js";

export function positionEllipse(covariance){
  if(!Array.isArray(covariance)||covariance.length!==9||!covariance.every(Number.isFinite))return null;
  const xx=covariance[0],xy=covariance[1]/2+covariance[3]/2,yy=covariance[4];
  const scale=Math.max(Math.abs(xx),Math.abs(xy),Math.abs(yy))||1;
  const x=xx/scale,y=yy/scale,cross=xy/scale;
  const radius=Math.hypot(x-y,2*cross),major=(x+y+radius)/2,minor=(x+y-radius)/2;
  if(xx<0||yy<0||major<0||minor<-Number.EPSILON*Math.max(1,major))return null;
  return {major:Math.sqrt(major)*Math.sqrt(scale),minor:Math.sqrt(Math.max(0,minor))*Math.sqrt(scale),angle:Math.atan2(2*cross,x-y)/2};
}

export class LocalizationHistory{
  constructor(profile,configuration){
    this.profile=profile;this.configuration=configuration??{};this.reset(null);
  }
  reset(context){this.context=context;this.gps=[];this.gpsTick=-1;this.candidates=new Map();this.lastSequence=-1;}
  update(view,now){
    const context=[view.run_id,view.payload.view_revision].join(":");
    if(context!==this.context)this.reset(context);
    if(view.sequence_number<=this.lastSequence)return;
    this.lastSequence=view.sequence_number;
    const fix=view.payload.local_observations?.find(m=>m.schema==="position_fix2d@1");
    if(this.configuration.gps_history_points&&fix&&fix.simulation_tick>this.gpsTick){
      this.gpsTick=fix.simulation_tick;
      this.gps.push([...fix.payload.position_m]);
      this.gps=this.gps.slice(-this.configuration.gps_history_points);
    }
    const current=new Set();
    for(const message of view.payload.pose_estimates??[]){
      const id=message.channel.split("/")[3];current.add(id);
      let candidate=this.candidates.get(id);
      if(!candidate){
        candidate={id,path:[],lastTick:-1,timeline:new SceneTimeline(this.profile.physics_hz,this.profile.rendering,this.profile.view.interpolation_jump_m)};
        this.candidates.set(id,candidate);
      }
      const synthetic={...view,payload:{...view.payload,selected_pose:{source_id:id,frame_id:message.frame_id,
        simulation_tick:message.simulation_tick,freshness:"fresh",pose:message.payload}}};
      const pushed=candidate.timeline.push(synthetic,now);
      if(pushed.poseJump)candidate.path=[];
      if(message.simulation_tick>candidate.lastTick){
        candidate.lastTick=message.simulation_tick;
        candidate.path.push([message.payload.x_m,message.payload.y_m]);
        candidate.path=candidate.path.slice(-(this.configuration.trail_points??this.profile.view.max_visual_trail));
      }
    }
    for(const id of this.candidates.keys())if(!current.has(id))this.candidates.delete(id);
  }
  sample(now){return [...this.candidates.values()].map(c=>({id:c.id,path:c.path,pose:c.timeline.sample(now).pose}));}
}

export function drawLocalization(ctx,point,frame,panel,scale){
  const history=panel.localization;
  if(!history)return;
  ctx.save();
  if(panel.enabled("gps")){
    ctx.strokeStyle="#f4cf7e";ctx.lineWidth=1.5;
    for(const fix of history.gps){const [x,y]=point(...fix);ctx.beginPath();ctx.moveTo(x-3,y);ctx.lineTo(x+3,y);ctx.moveTo(x,y-3);ctx.lineTo(x,y+3);ctx.stroke();}
    ctx.fillStyle="#f4cf7e";ctx.font="11px monospace";ctx.fillText("+ 带噪 GPS",12,72);
  }
  if(panel.enabled("pose_estimates")){
    const selected=panel.message?.payload.selected_pose?.source_id;
    for(const candidate of history.sample(panel.renderNow)){
      if(candidate.id===selected)continue;
      ctx.strokeStyle="#74b9ff";ctx.fillStyle="#74b9ff";ctx.lineWidth=2;ctx.setLineDash([5,4]);
      ctx.beginPath();candidate.path.forEach((p,i)=>i?ctx.lineTo(...point(...p)):ctx.moveTo(...point(...p)));ctx.stroke();ctx.setLineDash([]);
      if(candidate.pose){
        const p=candidate.pose,[x,y]=point(p.x_m,p.y_m);
        ctx.beginPath();ctx.arc(x,y,4,0,2*Math.PI);ctx.stroke();
        ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+14*Math.cos(p.yaw_rad),y-14*Math.sin(p.yaw_rad));ctx.stroke();
        ctx.font="11px monospace";ctx.fillText(history.configuration.pose_labels?.[candidate.id]??candidate.id,x+8,y-8);
      }
    }
  }
  if(panel.enabled("pose_covariance")&&frame.pose){
    const ellipse=positionEllipse(frame.pose.covariance);
    if(ellipse){
      ctx.translate(...point(frame.pose.x_m,frame.pose.y_m));ctx.rotate(-ellipse.angle);
      ctx.strokeStyle="#b8e4ca";ctx.fillStyle="#8fe3b51c";ctx.lineWidth=1.5;
      ctx.beginPath();ctx.ellipse(0,0,ellipse.major*scale,ellipse.minor*scale,0,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.rotate(ellipse.angle);ctx.font="10px monospace";ctx.fillStyle="#b8e4ca";ctx.fillText("1σ",8,-12);
    }
  }
  ctx.restore();
}
