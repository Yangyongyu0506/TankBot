export function timingRows(report){
  if(!report)return [];
  const names={round_trip_ms:'整批往返',request_encode_ms:'宿主请求编码',request_write_ms:'请求写入',response_decode_ms:'宿主响应解码',gate_wait_ms:'收到后等待提交门',runtime_python_ms:'Worker Python整批',worker_decode_ms:'Worker输入JSON解码',worker_encode_previous_ms:'Worker前批输出编码',bridge_round_trip_ms:'浏览器桥接往返',elapsed_to_failure_ms:'故障前经过'};
  return Object.entries(report.costs).filter(([,v])=>v.count).map(([key,value])=>({name:names[key]??key,...value}));
}
export function renderTiming(root,report){
  if(!root||!report)return;
  const summary=document.createElement('p');summary.className='hint';summary.textContent=`${report.backend} · 最近${report.window_batches}批 / 总${report.total_batches}批 · 超时${report.timeouts}（${(report.timeout_rate*100).toFixed(1)}%）· 原预算${report.budget_ms}ms。诊断不改变配额或固定提交。`;
  const table=document.createElement('table');
  for(const values of [['阶段 / ms','p50','p95','p99'],...timingRows(report).map(r=>[r.name,r.p50_ms,r.p95_ms,r.p99_ms]),...Object.entries(report.modules).flatMap(([mid,parts])=>Object.entries(parts).map(([key,r])=>[`${mid} · ${key}`,r.p50_ms,r.p95_ms,r.p99_ms]))]){
    const row=document.createElement('tr');for(const value of values){const cell=document.createElement('td');cell.textContent=typeof value==='number'?value.toFixed(3):value;row.append(cell);}table.append(row);
  }
  const pre=document.createElement('pre');pre.textContent=JSON.stringify(report.recent.map(r=>({step:r.step_id,samples:r.sample_ticks,activation:r.activation_tick,commit:r.commit_tick,received_monotonic_s:r.received_monotonic_s,gate_monotonic_s:r.commit_monotonic_s,status:r.status,where:r.failure_location,previous_encode_step:r.worker_encode_previous_step_id})),null,2);
  root.replaceChildren(summary,table,pre);
}
