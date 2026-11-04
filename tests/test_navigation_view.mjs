import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {WaypointOverlay,drawWaypoints} from '../web/navigation-view.js';
const config=JSON.parse(readFileSync(new URL('../core/tests/fixtures/default-profile.json',import.meta.url)));
const level=config.campaign.levels['navigation.c3'];
function profile(allowed=true){return {campaign:{active_level:'navigation.c3',levels:[{level_id:'navigation.c3',allowed_layers:allowed?['waypoints']:[],navigation:{...level.rules.waypoint_route,initial_xy_m:[0,0]},visualization:level.visualization}]}};}

test('public route and discrete progress determine goals without a robot pose',()=>{
  const view=new WaypointOverlay(profile());
  assert.equal(view.points().length,4);assert.ok(view.points().every(p=>p.status==='pending'));
  view.update('a',{goal_index:1,reached_count:1,total:4,complete:false});
  assert.deepEqual(view.points().map(p=>p.status),['reached','current','pending','pending']);
  view.update('a',{goal_index:3,reached_count:4,total:4,complete:false});
  assert.equal(view.points()[3].status,'current');
  view.update('a',{goal_index:3,reached_count:4,total:4,complete:true});
  assert.ok(view.points().every(p=>p.status==='reached'));
});

test('new runs, missing progress and denied layers cannot reuse old goal state',()=>{
  const view=new WaypointOverlay(profile());view.update('a',{goal_index:3,reached_count:4,complete:true});
  view.update('b',null);assert.ok(view.points().every(p=>p.status==='pending'));
  view.update('b',{goal_index:99,reached_count:99});assert.equal(view.state,null);
  const denied=new WaypointOverlay(profile(false));denied.update('a',{goal_index:0,reached_count:0});assert.deepEqual(denied.points(),[]);
});

test('drawing uses only public coordinates and follows the layer switch',()=>{
  const navigation=new WaypointOverlay(profile());navigation.update('run',{goal_index:0,reached_count:0,complete:false});
  const calls=[];const ctx=new Proxy({},{set(target,key,value){target[key]=value;return true;},get(target,key){return key in target?target[key]:(...args)=>calls.push([key,...args]);}});
  drawWaypoints(ctx,(x,y)=>[100*x,100*y],{enabled:()=>false,navigation},100);assert.equal(calls.length,0);
  drawWaypoints(ctx,(x,y)=>[100*x,100*y],{enabled:()=>true,navigation},100);
  assert.ok(calls.some(row=>row[0]==='arc'&&Math.abs(row[3]-35)<1e-10));
  assert.equal(calls.filter(row=>row[0]==='fillText').length,4);
  assert.ok(calls.some(row=>row[0]==='moveTo'&&row[1]===0&&row[2]===0));
});
