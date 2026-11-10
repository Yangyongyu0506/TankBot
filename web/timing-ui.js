export function timingRows(report){
  if(!report)return [];
  const names={round_trip_ms:'整批往返（完整解码）',response_arrival_ms:'迟到字节到达（未解码）',request_encode_ms:'宿主请求编码',request_queue_ms:'请求写入排队',request_write_ms:'请求写入',response_decode_ms:'宿主响应解码',response_delivery_ms:'解码后交付等待',gate_wait_ms:'收到至提交（含门等待与校验）',runtime_python_ms:'Worker Python整批',batch_module_update_ms:'同批模块 update 合计',worker_decode_ms:'Worker输入JSON解码',worker_encode_previous_ms:'Worker前批输出编码',bridge_round_trip_ms:'浏览器桥接往返',elapsed_to_failure_ms:'故障前经过'};
  return Object.entries(report.costs).filter(([,v])=>v.count).map(([key,value])=>({name:names[key]??key,...value}));
}
export function renderTiming(root,report){
  if(!root||!report)return;
  const p=report.execution_profile;
  const summary=document.createElement('p');summary.className='hint';summary.textContent=`${report.backend} · ${p?`${p.profile_id}@${p.profile_version}（${p.status}）· 声明总上限 ${p.module_declared_budget_cap_ms}ms · `:''}整批墙钟截止 ${report.batch_wall_deadline_ms??report.budget_ms}ms · 最近${report.window_batches}批 / 总${report.total_batches}批 · 截止故障${report.timeouts}（${(report.timeout_rate*100).toFixed(1)}%）。墙钟不是 CPU 时间，模块自报仅供诊断；浏览器0ms可能来自时钟量化，固定提交门不变。`;
  const table=document.createElement('table');
  for(const values of [['阶段 / ms','p50','p95','p99','p99.9','最大'],...timingRows(report).map(r=>[r.name,r.p50_ms,r.p95_ms,r.p99_ms,r.p99_9_ms,r.max_ms]),...Object.entries(report.modules).flatMap(([mid,parts])=>Object.entries(parts).map(([key,r])=>[`${mid} · ${key}`,r.p50_ms,r.p95_ms,r.p99_ms,r.p99_9_ms,r.max_ms]))]){
    const row=document.createElement('tr');for(const value of values){const cell=document.createElement('td');cell.textContent=typeof value==='number'?value.toFixed(3):(value??'—');row.append(cell);}table.append(row);
  }
  const scroll=document.createElement('div');scroll.className='runtime-timing-table';scroll.append(table);
  const pre=document.createElement('pre');pre.textContent=JSON.stringify(report.recent.map(r=>({step:r.step_id,phase:r.phase,samples:r.sample_ticks,activation:r.activation_tick,commit:r.commit_tick,started_monotonic_ns:r.started_monotonic_ns,deadline_monotonic_ns:r.deadline_monotonic_ns,received_monotonic_s:r.received_monotonic_s,gate_monotonic_s:r.commit_monotonic_s,status:r.status,where:r.failure_location,censored:r.censored,previous_encode_step:r.worker_encode_previous_step_id})),null,2);
  root.replaceChildren(summary,scroll,pre);
}
