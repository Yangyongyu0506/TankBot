import test from 'node:test';
import assert from 'node:assert/strict';
import {controlKeys,setBindings,controlKey,shortcut,keyLabel,validCode,bindingHint} from '../web/keyboard.js';
import {manualTargets} from '../web/gamepad.js';
import {allowedLayers,developerView,layerLabels} from '../web/visualization.js';
import {readFileSync} from 'node:fs';

const config=JSON.parse(readFileSync(new URL('../config/m1.json',import.meta.url)));

test('remapped physical keys preserve chassis semantics and release old bindings',()=>{
  setBindings({...controlKeys,forward:'ArrowUp',left:'ArrowLeft',editor:'F3',help:'F4',settings:'F9'});
  assert.equal(controlKey('KeyW'),null);assert.equal(controlKey('ArrowUp'),'KeyW');
  assert.equal(controlKey('F3'),null);
  for(const chassis of ['differential','omnidirectional']){
    const profile={chassis,view:config.view};
    const command=manualTargets(profile,new Set([controlKey('ArrowUp'),controlKey('ArrowLeft')]));
    assert.equal(command.twist.linear.x,config.view.keyboard_linear_mps);
    assert.equal(command.twist.linear.y,chassis==='omnidirectional'?config.view.keyboard_linear_mps:0);
    assert.equal(command.twist.angular.z,chassis==='differential'?config.view.keyboard_yaw_radps:0);
  }
  assert.ok(shortcut({code:'F3'},'editor'));
  for(const modifier of ['ctrlKey','altKey','metaKey','shiftKey','isComposing'])assert.ok(!shortcut({code:'F3',[modifier]:true},'editor'));
  assert.ok(!validCode('ControlLeft'));assert.ok(validCode('ArrowUp'));assert.equal(keyLabel('KeyW'),'W');
  assert.equal(bindingHint('W/S 前后；F2 编辑，F1 说明，空格单发。'),'↑/S 前后；F3 编辑，F4 说明，空格单发。');
  setBindings({});
});

test('player display choices never expose developer layers or forbidden projectile truth',()=>{
  const profile=level=>({campaign:{active_level:level,levels:Object.entries(config.campaign.levels).map(([level_id,v])=>({level_id,...v}))},view_mode:'campaign',radar_calibration:level==='c0'?null:{}});
  const c1=allowedLayers(profile('c1'),false);
  for(const key of ['truth_robot','truth_targets','projectiles','velocities','colliders'])assert.ok(!c1.includes(key));
  assert.ok(c1.includes('target_estimates'));assert.ok(c1.includes('radar'));
  assert.ok(allowedLayers(profile('c0'),false).includes('truth_targets'));
  assert.deepEqual(allowedLayers(profile('c2'),true),Object.keys(layerLabels));
});

test('developer projection keeps estimated and true states independent',()=>{
  const data={run_id:'one',simulation_tick:4,sensors:{},truth:{truth_pose:[1,2,.3],projectiles:[{projectile_id:1,position:[3,4]}],targets:[{target_id:'a',pose:[5,6,.7],alive:true},{target_id:'dead',alive:false}],target_hits:{a:2}}};
  const view=developerView(data,{projectile_radius_m:.03});
  assert.equal(view.payload.selected_pose.pose.x_m,1);
  assert.equal(view.payload.objects.length,2);
  assert.equal(view.payload.objects[0].radius_m,.03);
  view.payload.selected_pose.pose.x_m=90;
  assert.equal(data.truth.truth_pose[0],1);
});
