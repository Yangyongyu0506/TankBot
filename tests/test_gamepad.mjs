import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {GamepadDriver,mapGamepad,manualTargets,radialDeadzone,moving} from '../web/gamepad.js';

const config=JSON.parse(readFileSync(new URL('../core/tests/fixtures/default-profile.json',import.meta.url)));
const settings=config.view.gamepad;
const pad=(index=0,id='Test standard controller')=>({index,id,connected:true,mapping:'standard',axes:[0,0,0,0],buttons:Array.from({length:17},()=>({value:0,pressed:false}))});
const press=(p,name,value=1)=>{p.buttons[settings.buttons[name]]={value,pressed:value>=settings.button_threshold};};
const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-12,`${actual} != ${expected}`);

test('radial deadzone suppresses drift, preserves direction, and caps diagonal speed',()=>{
  assert.deepEqual(radialDeadzone(.03,-.1,settings.deadzone),[0,0]);
  const [x,y]=radialDeadzone(1,1,settings.deadzone);near(x,y);near(Math.hypot(x,y),1);
  const p=pad();p.axes[1]=-.59;near(mapGamepad(p,settings,'differential').vx,.5*settings.linear_mps);
});

test('both chassis use configured signs and scales, differential never emits vy',()=>{
  const p=pad();p.axes[0]=1;p.axes[2]=-1;
  const diff=mapGamepad(p,settings,'differential'),omni=mapGamepad(p,settings,'omnidirectional');
  assert.equal(diff.vy,0);assert.equal(diff.wz,-settings.yaw_radps);
  assert.equal(omni.vy,-settings.linear_mps);assert.equal(omni.wz,0);
  assert.equal(diff.turret,settings.turret_radps);
  press(p,'yaw_left');assert.equal(mapGamepad(p,settings,'omnidirectional').wz,settings.yaw_radps);
  press(p,'yaw_right');assert.equal(mapGamepad(p,settings,'omnidirectional').wz,0);
  const custom=structuredClone(settings);custom.standard_mapping_only=false;custom.axes.forward={index:3,sign:1};custom.buttons.fire=0;
  p.mapping='';p.axes[0]=0;p.axes[3]=1;p.buttons[0].value=1;
  assert.equal(mapGamepad(p,custom,'differential').vx,custom.linear_mps);
  assert.equal(mapGamepad(p,custom,'differential').fire,true);
});

test('fire is one edge, not repeat, including threshold and cooldown-independent holds',()=>{
  const d=new GamepadDriver(settings,'differential'),p=pad();d.sample([p]);
  press(p,'fire',settings.button_threshold-.01);assert.equal(d.sample([p]).fire,false);
  press(p,'fire');assert.equal(d.sample([p]).fire,true);
  for(let i=0;i<120;i++)assert.equal(d.sample([p]).fire,false);
  press(p,'fire',0);d.sample([p]);press(p,'fire');assert.equal(d.sample([p]).fire,true);
});

test('connection, reconnect and resume cannot arm while axes or trigger are held',()=>{
  const d=new GamepadDriver(settings,'differential'),p=pad();p.axes[1]=-1;press(p,'fire');
  assert.equal(d.sample([p]).status,'neutral');assert.equal(d.sample([p]).fire,false);
  p.axes[1]=0;press(p,'fire',0);assert.equal(d.sample([p]).status,'ready');
  p.axes[1]=-1;assert.ok(d.sample([p]).vx>0);
  const disconnected=d.sample([]);assert.equal(moving(disconnected),false);assert.equal(disconnected.fire,false);
  assert.equal(d.sample([p]).status,'neutral');
  p.axes[1]=0;d.sample([p]);press(p,'fire');
  assert.equal(d.sample([p],{uiAllowed:false}).fire,false);
  assert.equal(d.sample([p]).fire,false);press(p,'fire',0);d.sample([p]);
  press(p,'fire');assert.equal(d.sample([p]).fire,true);
});

test('editor toggle works inside modal, while driving and fire require neutral again',()=>{
  const d=new GamepadDriver(settings,'differential'),p=pad();d.sample([p]);
  press(p,'editor');assert.equal(d.sample([p]).editor,true);d.suspend();
  assert.equal(d.sample([p],{motionAllowed:false}).editor,false);
  press(p,'editor',0);press(p,'fire');p.axes[1]=-1;d.sample([p],{motionAllowed:false});
  press(p,'editor');const close=d.sample([p],{motionAllowed:false});assert.equal(close.editor,true);assert.equal(close.fire,false);
  const resumed=d.sample([p]);assert.equal(resumed.status,'neutral');assert.equal(moving(resumed),false);assert.equal(resumed.fire,false);
  press(p,'editor',0);press(p,'fire',0);p.axes[1]=0;d.sample([p]);
  p.axes[1]=-1;assert.ok(d.sample([p]).vx>0);
});

test('sparse devices, stable selection, replacements, disable, and unsupported input',()=>{
  const d=new GamepadDriver(settings,'omnidirectional'),a=pad(2),b=pad(4,'Second');
  assert.equal(d.sample([null,null,a,null,b]).device.index,2);
  d.select(4);assert.equal(d.sample([a,b]).device.index,4);
  assert.equal(d.sample([a]).device,null,'explicit selection must not silently take another device');
  assert.equal(d.sample([a,b]).status,'ready');b.id='Replacement';b.axes[1]=-1;
  assert.equal(d.sample([a,b]).status,'neutral');
  d.setEnabled(false);assert.equal(moving(d.sample([a,b])),false);
  d.setEnabled(true);assert.equal(d.sample([a,b]).status,'neutral');
  b.mapping='';assert.equal(d.sample([a,b]).status,'unsupported');b.mapping='standard';
  b.axes[1]=NaN;assert.equal(d.sample([a,b]).status,'unsupported');b.axes[1]=0;b.buttons=[];
  assert.equal(d.sample([a,b]).status,'unsupported');
  assert.equal(new GamepadDriver(undefined,'differential').sample([]).status,'disabled');
});

test('keyboard priority is per actuator, gated frames are zero, and targets stay Twist',()=>{
  const profile={chassis:'omnidirectional',view:config.view},p={vx:.7,vy:.4,wz:.3,turret:.9};
  let target=manualTargets(profile,new Set(['KeyW']),p);
  assert.equal(target.twist.linear.x,config.view.keyboard_linear_mps);assert.equal(target.twist.linear.y,0);assert.equal(target.twist.angular.z,0);
  assert.equal(target.turret.velocity_radps,.9,'keyboard drive does not discard gamepad turret');
  target=manualTargets(profile,new Set(['KeyJ']),p);
  assert.equal(target.twist.linear.y,.4);assert.equal(target.turret.velocity_radps,config.view.keyboard_turret_radps);
  const blocked=manualTargets(profile,new Set(['KeyW','KeyJ']),p,false);
  assert.equal(blocked.active,false);assert.deepEqual(blocked.twist,{linear:{x:0,y:0,z:0},angular:{x:0,y:0,z:0}});
});
