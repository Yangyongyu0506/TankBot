import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {LocalizationHistory,positionEllipse} from '../web/localization-view.js';
import {SceneTimeline} from '../web/rendering.js';

const config=JSON.parse(readFileSync(new URL('../core/tests/fixtures/default-profile.json',import.meta.url)));
const profile={physics_hz:60,rendering:config.rendering,view:config.view};
const covariance=[4,0,0,0,1,0,0,0,.01];
function view(tick,run='one',revision=0){
  return {run_id:run,simulation_tick:tick,sequence_number:tick,payload:{view_revision:revision,
    selected_pose:{source_id:'ekf',frame_id:'map',simulation_tick:tick,freshness:'fresh',pose:{x_m:tick/60,y_m:0,yaw_rad:0,covariance}},
    local_observations:[{schema:'position_fix2d@1',simulation_tick:tick,payload:{position_m:[tick,1]}}],objects:[],
    pose_estimates:[{schema:'pose2d@1',channel:'/robot/estimates/odometry/pose',simulation_tick:tick,frame_id:'map',payload:{x_m:tick/60,y_m:1,yaw_rad:0}}]}};
}

test('position ellipse derives principal one-sigma axes without assuming isotropic covariance',()=>{
  assert.deepEqual(positionEllipse(covariance),{major:2,minor:1,angle:0});
  const e=positionEllipse([2,1,0,1,2,0,0,0,1]);
  assert.ok(Math.abs(e.major-Math.sqrt(3))<1e-12);assert.ok(Math.abs(e.minor-1)<1e-12);assert.equal(e.angle,Math.PI/4);
  assert.equal(positionEllipse(null),null);assert.equal(positionEllipse([-1,0,0,0,1,0,0,0,1]),null);
  assert.equal(positionEllipse([1,3,0,3,1,0,0,0,1]),null);
  const huge=positionEllipse([1e308,1e308,0,1e308,1e308,0,0,0,1]);
  assert.ok(Number.isFinite(huge.major)&&Number.isFinite(huge.minor));
});

test('GPS and pose histories stay bounded, duplicate polling adds nothing and revisions reset',()=>{
  const history=new LocalizationHistory(profile,{gps_history_points:3,trail_points:4});
  for(let tick=0;tick<60;tick+=6){history.update(view(tick),tick*1000/60);history.update(view(tick),tick*1000/60);}
  assert.equal(history.gps.length,3);assert.equal(history.candidates.get('odometry').path.length,4);
  assert.equal(history.sample(950)[0].id,'odometry');
  history.update(view(0,'two'),1000);assert.deepEqual(history.gps,[[0,1]]);
  history.update(view(6,'two',1),1100);assert.deepEqual(history.gps,[[6,1]]);
  const denied=view(12,'two',1);denied.payload.pose_estimates=[];history.update(denied,1200);
  assert.equal(history.candidates.size,0);
});

test('GPS repeated cached measurements are not duplicated at render frequency',()=>{
  const history=new LocalizationHistory(profile,{gps_history_points:3,trail_points:4});
  const first=view(0);history.update(first,0);
  const second=view(6);second.payload.local_observations=first.payload.local_observations;history.update(second,100);
  assert.equal(history.gps.length,1);
  second.payload.local_observations[0].payload.position_m[0]=999;
  assert.equal(history.gps[0][0],0);
});

test('pose covariance is interpolated as a convex matrix, independently of true world state',()=>{
  const timeline=new SceneTimeline(60,profile.rendering,100);
  const a=view(0),b=view(12);b.payload.selected_pose.pose.covariance=covariance.map(v=>v*2);
  timeline.push(a,0);timeline.push(b,200);
  const sampled=timeline.sample(200+profile.rendering.estimate_interpolation_delay_ms-100);
  assert.ok(sampled.pose.covariance[0]>4&&sampled.pose.covariance[0]<8);
  assert.equal(sampled.pose.covariance.length,9);assert.equal(a.payload.selected_pose.pose.covariance[0],4);
});
