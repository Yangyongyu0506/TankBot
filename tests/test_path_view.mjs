import test from 'node:test';
import assert from 'node:assert/strict';
import {PathOverlay,drawPath} from '../web/path-view.js';
import {attemptSummary,pathResultSummary} from '../web/campaign-ui.js';

function profile(allowed=['path','checkpoints']){
  return {campaign:{active_level:'plugin.path',levels:[{level_id:'plugin.path',allowed_layers:allowed,
    path_tracking:{path_id:'ref-1',points_m:[[0,0],[1,0],[2,1]],checkpoints_m:[[0,0],[1,0],[2,1]],checkpoint_radius_m:.5},
    visualization:{path_tracking:{route_color:'r',current_color:'c',pending_color:'p',reached_color:'d',start_color:'s',end_color:'e',
      line_width_px:2,marker_radius_px:4,font_size_px:12,tolerance_color:'t'}}}]}};
}

test('public paths and ordered checkpoint state are independent of a selected robot pose',()=>{
  const overlay=new PathOverlay(profile());
  overlay.update('run',{path_id:'ref-1',reached_count:1});
  assert.deepEqual(overlay.points().map(p=>p.status),['reached','current','pending']);
  overlay.update('new-run',null);assert.equal(overlay.state,null);
  overlay.update('new-run',{path_id:'other',reached_count:2});assert.equal(overlay.state,null);
  overlay.update('new-run',{path_id:'ref-1',reached_count:999});assert.equal(overlay.state,null);
});

test('path and checkpoints have independent switches and cannot exceed their layer permissions',()=>{
  const seen=[];const ctx=new Proxy({}, {get:(obj,k)=>k in obj?obj[k]:(...args)=>seen.push([k,...args]),set:(obj,k,v)=>(obj[k]=v,true)});
  const overlay=new PathOverlay(profile());const panel={pathTracking:overlay,enabled:key=>key==='path'};
  drawPath(ctx,(x,y)=>[x,y],panel,10);
  assert.ok(seen.some(([key])=>key==='lineTo'));assert.ok(seen.some(([key,label])=>key==='fillText'&&label==='终点'));
  seen.length=0;panel.enabled=key=>key==='checkpoints';drawPath(ctx,(x,y)=>[x,y],panel,10);
  assert.ok(!seen.some(([key])=>key==='lineTo'));assert.ok(seen.some(([key,label])=>key==='fillText'&&label==='1'));
  seen.length=0;panel.pathTracking=new PathOverlay(profile([]));panel.enabled=()=>true;drawPath(ctx,(x,y)=>[x,y],panel,10);
  assert.ok(!seen.some(([key])=>['arc','lineTo'].includes(key)));
});

test('terminal reasons distinguish contact, excessive deviation and final RMSE',()=>{
  for(const [reason,fragment] of [['collision','接触'],['path_deviation','偏离'],['tracking_error','RMSE']]){
    assert.ok(attemptSummary({status:'ended',result:{reason},timing:{}}).includes(fragment));
  }
});

test('terminal task metrics remain independent when individual visualization grants are revoked',()=>{
  assert.equal(pathResultSummary({}), '');
  assert.equal(pathResultSummary({tracking_rmse_m:.123}), ' 全程追踪RMSE 0.1230 m。');
  assert.equal(pathResultSummary({max_deviation_m:.4}), ' 最大偏离 0.4000 m。');
  assert.ok(!pathResultSummary({tracking_samples:10}).includes('RMSE'));
  assert.equal(pathResultSummary({scored_duration_s:2}), ' 计分 2.00 s。');
});

test('an unrelated course without path state keeps the path layer empty',()=>{
  const overlay=new PathOverlay({campaign:{active_level:'weapons',levels:[]}});
  overlay.update('run-a',undefined);
  assert.equal(overlay.state,null);
  assert.deepEqual(overlay.points(),[]);
});
