import test from 'node:test';
import assert from 'node:assert/strict';
import {PlanningOverlay,drawPlanning} from '../web/global-planning-view.js';
import {attemptSummary,pathResultSummary} from '../web/campaign-ui.js';

function profile(allowed=['planning_map','safety_grid','path']){
  return {campaign:{active_level:'plugin.plan',levels:[{level_id:'plugin.plan',allowed_layers:allowed,
    global_planning:{task_id:'task',start_xy:[0,0],goal_xy:[1,1],map:{grid:[[true,false],[false,false]],origin_xy:[-1,-1],resolution_m:.2},inflated_grid:[[true,true],[true,false]]},
    visualization:{global_planning:{route_color:'r',raw_color:'w',inflated_color:'s',start_color:'a',goal_color:'b',grid_alpha:.2,line_width_px:2,font_size_px:12,marker_radius_px:4}}}]}};
}
const route={task_id:'task',path_id:'path',points_m:[[0,0],[.1,.1]],length_m:.14};
test('validated route is bound to both task and run; old test output stays invisible',()=>{
  const overlay=new PlanningOverlay(profile());
  overlay.update('run',{task_id:'task',route});assert.deepEqual(overlay.route,route);
  overlay.update('other',null);assert.equal(overlay.route,null);
  overlay.update('other',{task_id:'old',route});assert.equal(overlay.route,null);
  overlay.update('other',{task_id:'task',route:{...route,task_id:'old'}});assert.equal(overlay.route,null);
});
test('raw map, normative inflation and player route each require their own layer',()=>{
  const calls=[],ctx=new Proxy({}, {get:(o,k)=>k in o?o[k]:(...a)=>calls.push([k,...a]),set:(o,k,v)=>(o[k]=v,true)});
  const overlay=new PlanningOverlay(profile());overlay.update('run',{task_id:'task',route});
  const panel={globalPlanning:overlay,enabled:key=>key==='safety_grid'};
  drawPlanning(ctx,(x,y)=>[x,y],panel);assert.equal(calls.filter(c=>c[0]==='fillRect').length,3);
  assert.ok(!calls.some(c=>c[0]==='lineTo'||c[0]==='arc'));
  calls.length=0;panel.enabled=key=>key==='path';drawPlanning(ctx,(x,y)=>[x,y],panel);
  assert.ok(calls.some(c=>c[0]==='lineTo'));assert.ok(!calls.some(c=>c[0]==='fillRect'));
  calls.length=0;panel.globalPlanning=new PlanningOverlay(profile([]));panel.enabled=()=>true;drawPlanning(ctx,(x,y)=>[x,y],panel);
  assert.ok(!calls.some(c=>['lineTo','arc','fillRect'].includes(c[0])));
});
test('planning failure and wall time remain distinct from periodic CPU or tracking grades',()=>{
  assert.match(attemptSummary({result:{reason:'planning_failed'},timing:{}}),/规划/);
  assert.match(pathResultSummary({planning_elapsed_ms:37}),/往返墙钟 37.00 ms/);
  assert.match(pathResultSummary({task_id:'task',path_length_m:13}),/诊断/);
});
