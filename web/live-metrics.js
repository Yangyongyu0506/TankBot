// Only consumes Authority-authorized aggregate feedback, never target truth.
export class MetricHistory{
  constructor(config){this.config=config;this.reset(null);}
  reset(runId){this.runId=runId;this.points=[];this.lastSamples=0;}
  update(runId,attempt){
    if(runId!==this.runId)this.reset(runId);
    const live=attempt?.live_metrics,value=live?.[this.config.metric],samples=live?.[this.config.count_key??"scored_samples"];
    if(!Number.isFinite(value)||value<0||!Number.isInteger(samples)||samples<1||samples<=this.lastSamples)return;
    this.lastSamples=samples;this.points.push({value,samples});
    this.points=this.points.slice(-this.config.history_points);
  }
  get latest(){return this.points.at(-1)??null;}
  get summary(){const point=this.latest;return point?`${this.config.label} ${point.value.toFixed(this.config.precision)} ${this.config.unit}`:"";}
  get polyline(){
    return metricPolyline(this.points,metricDomain(this.points));
  }
}

export function metricDomain(...series){
  const points=series.flat();
  return {first:points.length?Math.min(...points.map(p=>p.samples)):0,last:Math.max(0,...points.map(p=>p.samples)),high:Math.max(0,...points.map(p=>p.value))||1};
}
export function metricPolyline(points,domain){
  return points.map(p=>`${1+98*(p.samples-domain.first)/Math.max(1,domain.last-domain.first)},${31-30*p.value/domain.high}`).join(" ");
}

export function mountLiveMetric(root,config){
  root.hidden=!config;
  if(!config)return {update(){},get summary(){return "";}};
  if(Array.isArray(config)){
    root.classList.add("multiple-metrics");
    const children=config.map(item=>{const child=document.createElement("div");root.append(child);return mountLiveMetric(child,item);});
    return {update(runId,attempt){children.forEach(child=>child.update(runId,attempt));},get summary(){return children.map(child=>child.summary).filter(Boolean).join(" · ");}};
  }
  const history=new MetricHistory(config);
  const reference=config.reference_metric?new MetricHistory({...config,metric:config.reference_metric,label:config.reference_label,count_key:"reference_samples"}):null;
  root.title=config.description;
  const title=document.createElement("span"),label=document.createElement("span"),value=document.createElement("strong"),unit=document.createElement("span"),count=document.createElement("small");
  title.className="live-metric-title";title.textContent=config.title;
  label.textContent=config.label;unit.textContent=config.unit;
  const number=document.createElement("div");number.className="live-metric-number";number.append(value,unit);
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg"),line=document.createElementNS(svg.namespaceURI,"polyline");
  svg.setAttribute("viewBox","0 0 100 34");svg.setAttribute("preserveAspectRatio","none");svg.setAttribute("role","img");
  svg.setAttribute("aria-label",config.label+"变化曲线，数值越低整体误差越小");svg.append(line);
  const referenceLine=reference?document.createElementNS(svg.namespaceURI,"polyline"):null,comparison=document.createElement("small");
  if(reference){referenceLine.style.stroke=config.reference_color;svg.append(referenceLine);comparison.style.color=config.reference_color;}
  root.replaceChildren(title,number,label,svg,count);
  if(reference)root.append(comparison);
  return {
    update(runId,attempt){
      history.update(runId,attempt);
      reference?.update(runId,attempt);
      const point=history.latest;
      value.textContent=point?point.value.toFixed(config.precision):"—";
      count.textContent=point?`${point.samples} 个有效样本 · ${attempt?.status==="active"?"实时累计":"已结束"}`:"等待程序发布有效估计";
      const domain=metricDomain(history.points,reference?.points??[]);
      line.setAttribute("points",metricPolyline(history.points,domain));
      if(reference){
        referenceLine.setAttribute("points",metricPolyline(reference.points,domain));
        comparison.textContent=reference.latest?reference.summary:"等待纯里程计对照";
        root.dataset.referenceValue=reference.latest?.value??"";
        root.dataset.referenceSamples=reference.latest?.samples??0;
      }
      root.dataset.samples=point?.samples??0;root.dataset.value=point?.value??"";
    },
    get summary(){return [history.summary,reference?.summary].filter(Boolean).join(" / ");}
  };
}
