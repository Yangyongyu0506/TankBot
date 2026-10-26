// Only consumes Authority-authorized aggregate feedback, never target truth.
export class MetricHistory{
  constructor(config){this.config=config;this.reset(null);}
  reset(runId){this.runId=runId;this.points=[];this.lastSamples=0;}
  update(runId,attempt){
    if(runId!==this.runId)this.reset(runId);
    const live=attempt?.live_metrics,value=live?.[this.config.metric],samples=live?.scored_samples;
    if(!Number.isFinite(value)||value<0||!Number.isInteger(samples)||samples<1||samples<=this.lastSamples)return;
    this.lastSamples=samples;this.points.push({value,samples});
    this.points=this.points.slice(-this.config.history_points);
  }
  get latest(){return this.points.at(-1)??null;}
  get summary(){const point=this.latest;return point?`${this.config.label} ${point.value.toFixed(this.config.precision)} ${this.config.unit}`:"";}
  get polyline(){
    const first=this.points[0],last=this.latest;
    if(!first||!last)return "";
    const high=Math.max(...this.points.map(p=>p.value))||1;
    return this.points.map(p=>`${1+98*(p.samples-first.samples)/Math.max(1,last.samples-first.samples)},${31-30*p.value/high}`).join(" ");
  }
}

export function mountLiveMetric(root,config){
  root.hidden=!config;
  if(!config)return {update(){},get summary(){return "";}};
  const history=new MetricHistory(config);
  root.title=config.description;
  const title=document.createElement("span"),label=document.createElement("span"),value=document.createElement("strong"),unit=document.createElement("span"),count=document.createElement("small");
  title.className="live-metric-title";title.textContent=config.title;
  label.textContent=config.label;unit.textContent=config.unit;
  const number=document.createElement("div");number.className="live-metric-number";number.append(value,unit);
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg"),line=document.createElementNS(svg.namespaceURI,"polyline");
  svg.setAttribute("viewBox","0 0 100 34");svg.setAttribute("preserveAspectRatio","none");svg.setAttribute("role","img");
  svg.setAttribute("aria-label",config.label+"变化曲线，数值越低整体误差越小");svg.append(line);
  root.replaceChildren(title,number,label,svg,count);
  return {
    update(runId,attempt){
      history.update(runId,attempt);
      const point=history.latest;
      value.textContent=point?point.value.toFixed(config.precision):"—";
      count.textContent=point?`${point.samples} 个有效样本 · ${attempt?.status==="active"?"实时累计":"已结束"}`:"等待程序发布有效估计";
      line.setAttribute("points",history.polyline);
      root.dataset.samples=point?.samples??0;root.dataset.value=point?.value??"";
    },
    get summary(){return history.summary;}
  };
}
