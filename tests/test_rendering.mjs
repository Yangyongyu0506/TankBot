import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {SceneTimeline, FollowCamera, drawChassis, omniMounts} from '../web/rendering.js';

const config = JSON.parse(readFileSync(new URL('../config/m1.json', import.meta.url)));
const settings = {...config.rendering, interpolation_delay_ms:100, estimate_interpolation_delay_ms:200};
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-12, `${actual} != ${expected}`);
const pose = (x, y=0, yaw=0) => ({x_m:x, y_m:y, yaw_rad:yaw});
const bullet = (id, x) => ({kind:'projectile', projectile_id:id, x_m:x, y_m:2, radius_m:.03});
function snapshot(tick, objects=[], location=pose(0), overrides={}) {
  const selected = location ? {source_id:'system', frame_id:'map', simulation_tick:tick, freshness:'fresh', pose:location} : null;
  return {run_id:'test', sequence_number:tick, simulation_tick:tick,
    payload:{view_revision:0, selected_pose:selected, objects, local_observations:[], effects:[]}, ...overrides};
}
const timeline = () => new SceneTimeline(60, settings, 1);

// Numerical behavior checks for a renderer that runs faster than incoming snapshots.
test('projectile positions vary on display frames between 10 Hz snapshots', () => {
  const t=timeline(); t.push(snapshot(0,[bullet(1,0)]),0); t.push(snapshot(6,[bullet(1,1.5)]),100);
  const middle=t.sample(150); assert.equal(middle.objects[0].x_m,.75);
  near(t.sample(160).objects[0].x_m,.9);
  near(t.sample(166).objects[0].x_m,.99);
});

test('interpolation uses simulation timestamps with uneven arrival and never extrapolates', () => {
  const t=timeline(); t.push(snapshot(0,[bullet(1,0)]),20); t.push(snapshot(3,[bullet(1,1)]),90);
  t.push(snapshot(9,[bullet(1,3)]),175);
  assert.equal(t.sample(175).objects[0].x_m,1);
  assert.equal(t.sample(225).objects[0].x_m,2);
  assert.equal(t.sample(5000).objects[0].x_m,3);
  const last=t.renderTime;
  t.push(snapshot(12,[bullet(1,4)]),5050);t.sample(5050);
  assert.ok(t.renderTime>=last,'late packets cannot rewind the displayed clock');
});

test('identity and snapshot boundaries control births and disappearance', () => {
  const t=timeline();t.push(snapshot(0),0);t.push(snapshot(6,[bullet(1,1)]),100);
  assert.equal(t.sample(150).objects.length,0,'do not show a bullet before its first authorized frame');
  assert.equal(t.sample(200).objects[0].x_m,1);
  t.push(snapshot(12),200);
  assert.equal(t.sample(250).objects.length,1);
  assert.equal(t.sample(300).objects.length,0,'a removed bullet must not become a ghost');
  t.push(snapshot(18,[bullet(2,8)]),300);
  assert.equal(t.sample(350).objects.length,0,'different IDs never interpolate into each other');
});

test('body and turret use their own sampling timestamps and respective angle conventions', () => {
  const t=timeline();
  const a=snapshot(0,[],pose(0,0,170*Math.PI/180));
  a.payload.local_observations=[{channel:'/robot/turret/joint_states',simulation_tick:0,payload:{position:[0]}}];
  const b=snapshot(6,[],pose(.5,0,-170*Math.PI/180));
  b.payload.local_observations=[{channel:'/robot/turret/joint_states',simulation_tick:6,payload:{position:[4*Math.PI]}}];
  t.push(a,0);t.push(b,100);const middle=t.sample(150);
  assert.equal(middle.pose.x_m,.25);assert.ok(Math.abs(middle.pose.yaw_rad-Math.PI)<1e-12);
  assert.equal(middle.turretAngle,2*Math.PI);
  const repeated=snapshot(12,[],pose(.5));repeated.payload.selected_pose.simulation_tick=6;
  t.push(repeated,200);assert.equal(t.poses.length,2,'view rate must not manufacture new algorithm samples');
});

test('a player estimate can lag the view while camera and body still interpolate together', () => {
  const t=timeline();
  for(const tick of [6,12,18]) {
    const msg=snapshot(tick,[],pose((tick-6)/60));
    msg.payload.selected_pose.source_id='odometry';msg.payload.selected_pose.simulation_tick=tick-6;
    t.push(msg,tick*1000/60);
  }
  const displayed=t.sample(350);near(displayed.pose.x_m,.15);
  const camera=new FollowCamera([0,0]);camera.follow(displayed.pose);
  assert.deepEqual(camera.project(displayed.pose.x_m,displayed.pose.y_m,1000,700,12),[500,350]);
});

test('camera follows xy, preserves world axes through yaw changes, and holds without pose', () => {
  const camera=new FollowCamera([0,0]);
  camera.follow(pose(3,-2,Math.PI/2));
  assert.deepEqual(camera.project(3,-2,1000,700,10),[500,350]);
  assert.deepEqual(camera.project(4,-1,1000,700,10),[600,250]);
  camera.follow(pose(3,-2,-Math.PI));
  assert.deepEqual(camera.project(4,-1,1000,700,10),[600,250]);
  camera.follow(null);assert.deepEqual([camera.x,camera.y],[3,-2]);
});

test('lost estimate, revision changes and pose jumps clear obsolete visual history', () => {
  const t=timeline();t.push(snapshot(0,[bullet(1,0)]),0);t.push(snapshot(6,[bullet(1,1)],pose(.5)),100);
  assert.equal(t.push(snapshot(3),110).accepted,false);
  const lost=t.push(snapshot(12,[],null),200);assert.equal(lost.reset,true);
  assert.equal(t.sample(220).pose,null);assert.equal(t.sample(220).objects.length,0);
  t.push(snapshot(18,[],pose(50)),300);assert.equal(t.sample(300).pose.x_m,50);
  assert.equal(t.push(snapshot(24,[],pose(100)),400).poseJump,true);
  assert.equal(t.sample(400).pose.x_m,100,'do not pan through an invalid interpolated relocation');
  const changed=snapshot(30);changed.payload.view_revision=1;
  assert.equal(t.push(changed,500).clearCamera,true);assert.equal(t.frames.length,1);
});

test('history is bounded without discarding a required lower endpoint', () => {
  const t=timeline();for(let tick=0;tick<12000;tick+=2)t.push(snapshot(tick),tick*1000/60);
  assert.ok(t.frames.length<=settings.history_ms/1000*30+2);
  assert.ok(t.poses.length<=settings.history_ms/1000*30+2);
});

test('independent chassis configurations draw tracks versus four radial omni wheels', () => {
  const differential=config.rendering.chassis_models.differential;
  const omni=config.rendering.chassis_models.omnidirectional;
  assert.notEqual(differential.model_id,omni.model_id);assert.notDeepEqual(differential.hull,omni.hull);
  assert.equal(differential.kind,'tracked');assert.equal(omni.kind,'radial_omni');
  const calibration={radius_m:config.wheels.radius_m,...config.wheels.omnidirectional};
  const mounts=omniMounts(calibration);
  assert.equal(mounts.length,4);assert.equal(omni.wheels,undefined,'visual config cannot duplicate wheel positions');
  for(const w of mounts) {
    near(Math.hypot(w.x_m,w.y_m),.25);
    near(w.x_m*Math.cos(w.drive_yaw_rad)+w.y_m*Math.sin(w.drive_yaw_rad),0);
    const rotated=mounts.find(p=>Math.hypot(p.x_m+w.y_m,p.y_m-w.x_m)<1e-12);
    assert.ok(rotated,'90-degree rotation must land on another complete wheel mount');
    near(Math.cos(rotated.drive_yaw_rad-w.drive_yaw_rad),0);
  }
  for(const model of [differential,omni]) {
    const calls=[];
    const ctx=new Proxy({}, {get:(_,name)=>(...args)=>calls.push([name,...args]),set:()=>true});
    drawChassis(ctx,model,100,false,calibration);
    assert.ok(calls.some(c=>c[0]==='roundRect'));
    if(model.kind==='radial_omni') {
      const rotations=calls.filter(c=>c[0]==='rotate').map(c=>c[1]);
      assert.equal(rotations.length,4);
      mounts.forEach((w,i)=>near(rotations[i],-w.drive_yaw_rad));
      assert.ok(calls.some(c=>c[0]==='roundRect' && Math.abs(c[3]-2*calibration.radius_m*100)<1e-12));
    }
    assert.equal(calls.filter(c=>c[0]==='clip').length,model.kind==='radial_omni'?4:0);
  }
});
