// Filter experiments receive authorized samples and derived errors, never evaluator truth.
export function curveGeometry(points,field,width=640,height=150){
  const values=points.map(field).filter(Number.isFinite),ticks=points.map(p=>p.tick);
  if(!values.length)return {path:"",minimum:null,maximum:null};
  const low=Math.min(...values),high=Math.max(...values),range=high-low||1;
  const first=Math.min(...ticks),last=Math.max(...ticks),span=last-first||1;
  let path="",previous=false;
  for(const point of points){const value=field(point);if(!Number.isFinite(value)){previous=false;continue;}
    const x=36+(width-48)*(point.tick-first)/span,y=height-24-(height-40)*(value-low)/range;
    path+=`${previous?" L":"M"} ${x.toFixed(3)},${y.toFixed(3)}`;previous=true;
  }
  return {path,minimum:low,maximum:high};
}
export function experimentComparison(reports){
  return reports.map(report=>({revision:report.revision,status:report.status,input:report.input_sha256,
    executed:report.points.length,rmse:report.rmse_m,samples:report.scored_samples,
    missing:report.points.filter(p=>p.missing).length,failure:report.failure}));
}
const $=id=>document.getElementById(id),ns="http://www.w3.org/2000/svg";
function node(tag,attributes={}){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attributes))n.setAttribute(k,String(v));return n;}
function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json"}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function plot(root,title,points,series,ui){
  const figure=document.createElement('figure'),caption=document.createElement('figcaption');caption.textContent=title;
  const svg=node('svg',{viewBox:`0 0 ${ui.plot_width} ${ui.plot_height}`,role:'img','aria-label':title+'，横轴为采样时间'});
  const first=points[0]?.time_s??0,last=points.at(-1)?.time_s??0;
  series.forEach(([label,value],i)=>{const geometry=curveGeometry(points,value,ui.plot_width,ui.plot_height);
    const line=node('path',{d:geometry.path,fill:'none',stroke:ui.series_colors[i], 'stroke-width':2});svg.append(line);
    const text=node('text',{x:38+i*180,y:14,fill:ui.series_colors[i]});text.textContent=label+(geometry.minimum===null?'（无发布）':` ${geometry.minimum.toFixed(3)}…${geometry.maximum.toFixed(3)}`);svg.append(text);
  });
  for(const [x,value] of [[36,first],[ui.plot_width-85,last]]){const text=node('text',{x,y:ui.plot_height-4});text.textContent=value.toFixed(2)+' s';svg.append(text);}
  figure.append(caption,svg);root.append(figure);
}
export function mountExperiments(browser,profile,releaseControls){
  const dialog=$('experiment-dialog');let token=profile.control_token,state,versions,pending=[],busy=false,pollTimer,lastReports='',wasRunning=false;
  const definition=profile.campaign?.levels.find(item=>item.level_id===profile.campaign.active_level);
  const enabled=Boolean(definition?.experiment);
  $('open-experiment').disabled=!enabled;$('open-experiment').title=enabled?'录制授权输入并比较两个保存版本':'本关未开放传感器回放实验';
  if(!enabled)return;
  async function runtime(operation,value={}){
    const path='/api/experiment/'+operation;
    const response=browser?await browser.post(path,value):await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':token},body:JSON.stringify(operation==='compare'?{revision:value.snapshot.revision}:value)});
    const result=await response.json();if(!response.ok)throw Error(result.error??'实验请求失败');return result;
  }
  async function workspace(operation,value={}){
    const response=await fetch('/api/workspace/'+operation,{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':token},body:JSON.stringify(value)});
    const result=await response.json();if(!response.ok)throw Error(result.error??'项目请求失败');return result;
  }
  async function action(fn){if(busy)return;busy=true;dialog.dataset.busy='true';render();try{await fn();}catch(error){$('experiment-message').textContent=error.message;pending=[];}finally{busy=false;dialog.dataset.busy='false';await poll();}}
  async function inventory(){
    const initial=await(await fetch('/api/workspace')).json();token=initial.control_token;
    versions=await workspace('revisions');
    for(const [id,index] of [['experiment-version-a',0],['experiment-version-b',1]]){
      const select=$(id),previous=select.value;select.replaceChildren(...versions.map(item=>{const option=document.createElement('option');option.value=item.revision;option.textContent=`${item.current?'当前 · ':''}${item.pinned?'固定 · ':''}${item.revision.slice(0,12)} · ${item.source_bytes} B`;return option;}));
      select.value=versions.some(v=>v.revision===previous)?previous:versions[Math.min(index,versions.length-1)].revision;
    }
    const records=await workspace('experiment_list'),select=$('experiment-saved');select.replaceChildren(...records.map(item=>{const o=document.createElement('option');o.value=item.id;o.textContent=`${item.id.slice(0,12)} · ${item.frames}批 · ${item.bytes} B`;return o;}));
    $('experiment-load').disabled=!records.length;
  }
  function render(){
    if(!state)return;
    const record=state.record;
    $('experiment-scope').textContent=`${definition.title} · 最多${state.limits.max_batches}批 / ${state.limits.max_record_bytes/1024} KiB。${definition.experiment.description} 可选diagnostic(name,value)，允许 ${Object.entries(definition.experiment.diagnostics).map(([name,size])=>`${name}(${size})`).join("、")}。`;
    $('experiment-record').textContent=record?`${state.recording?'录制中':'已停止'} · ${state.frames}批 · revision ${record.source_revision.slice(0,12)} · seed ${record.seed} · 部署tick ${record.deployment_tick??'—'} · 录制tick ${record.recording_start_tick} · ${record.stop_reason??'等待停止'}${state.private_scoring_available?' · 当前会话可计算误差':' · 导入记录无私有评分参考，新误差显示为空'}`:'请正式部署算法，再开始录制；编辑和准备时间不会被冒充一致的实验起点。';
    for(const id of ['experiment-start','experiment-import'])$(id).disabled=busy||Boolean(state.job)||state.recording;
    $('experiment-stop').disabled=busy||!state.recording;
    for(const id of ['experiment-compare','experiment-clear','experiment-save','experiment-export'])$(id).disabled=busy||Boolean(state.job)||state.recording||!state.frames;
    if(state.job){$('experiment-message').textContent=`正在执行 ${state.job.revision.slice(0,12)} · ${state.job.phase} · ${state.job.completed_frames}/${state.frames}批`;wasRunning=true;}
    else if(wasRunning){$('experiment-message').textContent=`比较结束 · ${state.comparisons.length} 个结果 · ${state.comparisons.filter(r=>r.status==='Failed').length} 个失败`;wasRunning=false;}
    const key=JSON.stringify(state.comparisons);if(key===lastReports)return;lastReports=key;
    const root=$('experiment-results');root.replaceChildren();
    for(const [index,report] of state.comparisons.entries()){
      const section=document.createElement('section'),title=document.createElement('h3'),summary=document.createElement('p');
      section.dataset.revision=report.revision;title.textContent=`版本 ${index?'B':'A'} · ${report.revision.slice(0,12)} · ${report.status}`;
      summary.textContent=`实际执行 ${report.points.length}/${state.frames}批 · ${report.scored_samples}评分样本 · 累计RMSE ${report.rmse_m===null?(state.private_scoring_available?'暂无有效估计':'无私有参考'):report.rmse_m.toFixed(4)+' m'} · 输入 ${report.input_sha256.slice(0,12)}`;
      const source=document.createElement('button');source.textContent='导出此版本源码（可在F2预览导入）';source.onclick=()=>download(report.source_snapshot,'tankbot-source-'+report.revision.slice(0,12)+'.json');
      section.append(title,summary,source);
      if(report.failure){const error=document.createElement('pre');error.className='experiment-error';error.textContent=`${JSON.stringify(report.failure)}\n${report.logs.map(e=>e.text).join('')}`;section.append(error);}
      const ui=state.ui;
      plot(section,'原始测量距离 / m',report.points,[['Radar r',p=>p.measurements[0]?.range_m]],ui);
      plot(section,'原始测量方位 / rad',report.points,[['Radar θ',p=>p.measurements[0]?.bearing_rad]],ui);
      plot(section,'地图系目标估计 / m',report.points,[['x',p=>p.estimate?.x_m],['y',p=>p.estimate?.y_m]],ui);
      plot(section,'估计协方差对角项 / m²',report.points,[['Pxx',p=>p.estimate?.covariance?.[0]],['Pyy',p=>p.estimate?.covariance?.[3]]],ui);
      plot(section,'误差 / m',report.points,[['采样误差',p=>p.error_m],['累计RMSE',p=>p.cumulative_rmse_m]],ui);
      const detail=document.createElement('details'),heading=document.createElement('summary'),pre=document.createElement('pre');heading.textContent='分段误差、缺测区间与可选诊断';
      pre.textContent=JSON.stringify({segments:report.segments,missing_intervals:report.missing_intervals,diagnostics:report.points.filter(p=>p.diagnostics.length).map(p=>({tick:p.tick,values:p.diagnostics}))},null,2);detail.append(heading,pre);section.append(detail);
      root.append(section);
    }
    root.dataset.completed=state.comparisons.length;
  }
  async function poll(schedule=true){
    clearTimeout(pollTimer);
    try{
      state=await runtime('status');render();
      if(pending.length&&!state.job){const snapshot=await workspace('revision',{revision:pending.shift()});state=await runtime('compare',{snapshot});render();}
    }catch(error){$('experiment-message').textContent=error.message;}
    if(schedule&&dialog.open)pollTimer=setTimeout(poll,state?.limits.poll_ms??profile.view.poll_ms);
  }
  $('open-experiment').onclick=()=>action(async()=>{releaseControls();dialog.showModal();await inventory();await poll();});
  $('close-experiment').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{clearTimeout(pollTimer);$('arena').focus();});
  $('experiment-start').onclick=()=>action(async()=>{state=await runtime('start');$('experiment-message').textContent='开始录制固定输入。停止后结束尝试，再比较版本。';});
  $('experiment-stop').onclick=()=>action(async()=>{state=await runtime('stop');});
  $('experiment-clear').onclick=()=>action(async()=>{pending=[];state=await runtime('clear');});
  $('experiment-compare').onclick=()=>action(async()=>{state=await runtime('clear');pending=[$('experiment-version-b').value];const snapshot=await workspace('revision',{revision:$('experiment-version-a').value});state=await runtime('compare',{snapshot});});
  $('experiment-export').onclick=()=>action(async()=>download(await runtime('export'),'tankbot-filter-reproduction.json'));
  $('experiment-save').onclick=()=>action(async()=>{await workspace('experiment_save',{package:await runtime('export')});$('experiment-message').textContent='已保存授权输入与失败记录；私有真值参考不导出。';await inventory();});
  $('experiment-load').onclick=()=>action(async()=>{const saved=await workspace('experiment_load',{id:$('experiment-saved').value});state=await runtime('import',{record:saved.record});});
  $('experiment-import').onchange=event=>action(async()=>{const file=event.target.files[0];if(!file)return;if(file.size>state.limits.max_record_bytes*4)throw Error('实验文件过大');const value=JSON.parse(await file.text());state=await runtime('import',{record:value.record??value});
    const root=$('experiment-imported-sources');root.replaceChildren();
    const note=document.createElement('p');note.className='hint';note.textContent='记录内源码不会自动加载。可导出一个版本，再在F2“导入项目并预览”中明确恢复。';root.append(note);
    const sources=[...(value.comparisons??[]).filter(r=>r.source_snapshot).map(r=>r.source_snapshot),...(value.record?.source_files?[{files:value.record.source_files,revision:value.record.source_revision}]:[])];
    for(const snapshot of sources){const button=document.createElement('button');button.textContent='导出源码 '+snapshot.revision.slice(0,12);button.onclick=()=>download(snapshot,'tankbot-source-'+snapshot.revision.slice(0,12)+'.json');root.append(button);}
    event.target.value='';});
  $('experiment-end-attempt').onclick=()=>action(async()=>{state=await runtime('stop');const response=browser?await browser.post('/api/campaign/finish',{}):await fetch('/api/campaign/finish',{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':token},body:'{}'});if(!response.ok)throw Error('结束尝试失败');$('experiment-message').textContent='正式尝试已结束；现在可以比较两个版本。';});
}
