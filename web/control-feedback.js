// Samples come only from the Authority's explicitly permitted control signals.
export class ControlHistory {
  constructor(config) { this.config=config; this.reset(null); }
  reset(runId) { this.runId=runId; this.points=[]; this.lastTick=-1; }
  update(runId,attempt) {
    if(runId!==this.runId)this.reset(runId);
    const points=attempt?.control_feedback?.points;
    if(!Array.isArray(points)||!points.length)return;
    const allowed=new Set(this.config.charts.flatMap(chart=>chart.signals.map(s=>s.signal)));
    const valid=points.filter(p=>Number.isSafeInteger(p.simulation_tick)&&Number.isSafeInteger(p.elapsed_ticks)&&p.elapsed_ticks>=0);
    if(!valid.length||valid.at(-1).simulation_tick<this.lastTick)return;
    const incoming=attempt.control_feedback.complete===false?[...this.points,...valid.filter(p=>p.simulation_tick>this.lastTick)]:valid;
    this.points=incoming.filter((p,i)=>!i||p.simulation_tick>incoming[i-1].simulation_tick).slice(-this.config.history_points).map(p=>({
      ...p,values:Object.fromEntries(Object.entries(p.values??{}).filter(([k,v])=>allowed.has(k)&&Number.isFinite(v)))
    }));
    this.lastTick=this.points.at(-1)?.simulation_tick??-1;
  }
  geometry(chart,durationTicks) {
    const values=this.points.flatMap(p=>chart.signals.map(s=>p.values[s.signal])).filter(Number.isFinite);
    const low=Math.min(0,...values),high=Math.max(0,...values),span=high-low||1;
    const min=low-span*.08,max=high+span*.08,range=max-min;
    const x=t=>42+430*t/Math.max(1,durationTicks),y=v=>98-82*(v-min)/range;
    const lines=chart.signals.map(s=>{
      let d="",previous=null;
      for(const point of this.points){
        const value=point.values[s.signal];
        if(!Number.isFinite(value)){previous=null;continue;}
        const px=x(point.elapsed_ticks),py=y(value);
        d+=previous===null?`M ${px},${py}`:(s.signal.startsWith("command_")||s.signal.endsWith("_voltage_v"))?` H ${px} V ${py}`:` L ${px},${py}`;
        previous=point;
      }
      return {signal:s.signal,d,color:s.color};
    });
    const markers=this.points.filter((p,i)=>i>0&&(p.cycle_index!==this.points[i-1].cycle_index||p.segment_index!==this.points[i-1].segment_index));
    return {lines,markers:markers.map(p=>({x:x(p.elapsed_ticks),label:p.label,tick:p.elapsed_ticks})),min,max,zero:y(0)};
  }
}

export function mountControlFeedback(root,config,physicsHz,durationTicks,expanded=false) {
  root.hidden=!config;
  if(!config)return {update(){}};
  const history=new ControlHistory(config),ns="http://www.w3.org/2000/svg";
  const node=(tag,attributes={})=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attributes))n.setAttribute(k,String(v));return n;};
  const title=document.createElement("h2"),note=document.createElement("p"),status=document.createElement("p");
  title.textContent=config.title;note.textContent=config.description;note.className="hint";status.className="control-plot-status";
  root.replaceChildren(title,note,status);
  let dialog,large,lastAttempt;
  if(!expanded){
    const button=document.createElement("button"),close=document.createElement("button"),content=document.createElement("div");
    button.id="expand-control";button.type="button";button.textContent="放大曲线";button.setAttribute("aria-haspopup","dialog");button.setAttribute("aria-controls","control-dialog");
    dialog=document.createElement("dialog");dialog.id="control-dialog";dialog.setAttribute("aria-label",config.title);
    close.id="close-control";close.type="button";close.textContent="×";close.setAttribute("aria-label","关闭控制曲线");
    content.className="control-expanded";dialog.append(close,content);document.body.append(dialog);root.insertBefore(button,note);
    large=mountControlFeedback(content,config,physicsHz,durationTicks,true);
    button.onclick=()=>{large.update(history.runId,{...lastAttempt,control_feedback:{points:history.points,complete:true}});dialog.showModal();};
    close.onclick=()=>dialog.close();
  }
  const plots=config.charts.map(chart=>{
    const figure=document.createElement("figure"),heading=document.createElement("figcaption"),name=document.createElement("strong");
    name.textContent=`${chart.title} / ${chart.unit}`;heading.append(name);figure.className="control-plot";
    const legend=document.createElement("div");legend.className="control-legend";
    const labels=chart.signals.map(signal=>{const label=document.createElement("span");label.style.color=signal.color;legend.append(label);return label;});
    const svg=node("svg",{viewBox:"0 0 480 120",role:"img","aria-label":`${chart.title}，横轴为仿真秒`});
    figure.append(heading,legend,svg);root.append(figure);
    const render=()=>{
      const g=history.geometry(chart,durationTicks);
      const zero=node("path",{d:`M 42 ${g.zero} H 472`,class:"control-zero"});
      const group=node("g");
      for(const marker of g.markers){
        const line=node("path",{d:`M ${marker.x} 12 V 98`,class:"control-phase"}),tip=node("title");
        tip.textContent=`${(marker.tick/physicsHz).toFixed(1)} s · ${marker.label}`;line.append(tip);group.append(line);
      }
      const texts=[[4,20,g.max.toFixed(config.precision)],[4,99,g.min.toFixed(config.precision)],
        [42,116,"0 s"],[240,116,`${(durationTicks/physicsHz/2).toFixed(1)} s`],[438,116,`${(durationTicks/physicsHz).toFixed(1)} s`]];
      svg.replaceChildren(zero,group,...g.lines.map(line=>node("path",{d:line.d,stroke:line.color,class:"control-line"})),...texts.map(([x,y,text])=>{const n=node("text",{x,y});n.textContent=text;return n;}));
    };
    const show=point=>labels.forEach((label,i)=>{const s=chart.signals[i],v=point?.values[s.signal];label.textContent=`${s.label} ${Number.isFinite(v)?v.toFixed(config.precision):"—"}`;});
    svg.addEventListener("pointermove",event=>{
      const rect=svg.getBoundingClientRect(),tick=Math.max(0,Math.min(1,((event.clientX-rect.left)/rect.width*480-42)/430))*durationTicks;
      const point=history.points.reduce((best,p)=>!best||Math.abs(p.elapsed_ticks-tick)<Math.abs(best.elapsed_ticks-tick)?p:best,null);
      show(point);if(point)svg.setAttribute("aria-label",`${chart.title}，${(point.elapsed_ticks/physicsHz).toFixed(2)} 仿真秒，${labels.map(l=>l.textContent).join("，")}`);
      figure.title=point?`${(point.elapsed_ticks/physicsHz).toFixed(2)} s · 第 ${point.cycle_index+1} 轮 ${point.label}`:"等待控制开始";
    });
    svg.addEventListener("pointerleave",()=>show(history.points.at(-1)));
    return ()=>{render();show(history.points.at(-1));};
  });
  return {get cursor(){return history.runId===null?{}:{control_after_tick:history.lastTick,run_id:history.runId};},update(runId,attempt){
    lastAttempt=attempt;
    history.update(runId,attempt);plots.forEach(render=>render());
    if(dialog?.open)large.update(runId,{...attempt,control_feedback:{points:history.points,complete:true}});
    const last=history.points.at(-1);
    status.textContent=last?`${attempt?.phase==="finished"?"已结束 · 曲线保留":"实时"} ${(last.elapsed_ticks/physicsHz).toFixed(2)} s · 第 ${last.cycle_index+1} 轮 ${last.label} · 移入曲线查看采样值`:"等待正式部署后的首批控制生效";
    root.dataset.samples=history.points.length;root.dataset.runId=runId??"";
  }};
}
