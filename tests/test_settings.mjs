import test from 'node:test';
import assert from 'node:assert/strict';
import {controlKeys,setBindings,controlKey,shortcut,keyLabel,validCode,bindingHint} from '../web/keyboard.js';
import {manualTargets} from '../web/gamepad.js';
import {allowedLayers,developerView,layerLabels,mountVisualization} from '../web/visualization.js';
import {readFileSync} from 'node:fs';

const config=JSON.parse(readFileSync(new URL('../core/tests/fixtures/default-profile.json',import.meta.url)));

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

test('Weapons allows projectile layers while keeping enemy and developer truth hidden',()=>{
  const profile=level=>({campaign:{active_level:level,levels:Object.entries(config.campaign.levels).map(([level_id,v])=>({level_id,...v}))},view_mode:'campaign',radar_calibration:level==='c0'?null:{}});
  for(const level of ['c1','c2','c3','c4','c5']){
    const allowed=allowedLayers(profile(level),false);
    for(const key of ['truth_robot','truth_targets','velocities','colliders'])assert.ok(!allowed.includes(key));
    for(const key of ['projectiles','target_estimates','radar'])assert.ok(allowed.includes(key));
  }
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

test('developer projection selects each target model without borrowing the player chassis',()=>{
  const visuals={omni:{chassis_visual:config.rendering.chassis_models.omnidirectional},tracked:{chassis_visual:config.rendering.chassis_models.differential}};
  const data={run_id:'one',simulation_tick:4,sensors:{},target_visuals:visuals,truth:{truth_pose:[0,0,0],projectiles:[],target_hits:{omni:0,tracked:1},targets:[{target_id:'omni',pose:[1,2,.7],alive:true},{target_id:'tracked',pose:[3,4,.1],alive:true}]}};
  const view=developerView(data,{projectile_radius_m:.03,chassis_visual:config.rendering.chassis_models.differential});
  assert.equal(view.payload.objects[0].visual,visuals.omni);
  assert.equal(view.payload.objects[1].visual,visuals.tracked);
});

test('developer display toggles are independent of campaign player restrictions',async()=>{
  const oldDocument=globalThis.document,oldWindow=globalThis.window;
  const element=()=>({append(...children){this.children=children;},replaceChildren(...children){this.children=children;},querySelector:()=>({}),dataset:{}});
  const nodes=new Map();
  globalThis.document={getElementById:id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},createElement:element,createTextNode:text=>({text})};
  globalThis.window={addEventListener(){}};
  try{
    const profile={physics_hz:60,rendering:config.rendering,view:config.view,campaign:{active_level:'plugin',levels:[{level_id:'plugin',allowed_layers:['map','radar'],visualization:{initial_enabled:['map'],user_toggleable:['radar'],preserve_user_settings:true}}]}};
    for(const developer of [false,true]){
      const panel=mountVisualization(profile,{value:{developer_mode:developer,layers:{map:true,truth_targets:true}},saveLayers:async()=>{}});
      const inputs=nodes.get('layer-list').children.map(label=>label.children[0]);
      if(developer){
        assert.ok(inputs.every(input=>!input.disabled));
        const truth=inputs.find(input=>input.dataset.layer==='truth_targets');
        assert.ok(panel.enabled('truth_targets'));truth.checked=false;truth.onchange();assert.ok(!panel.enabled('truth_targets'));
      }else{
        assert.equal(inputs.find(input=>input.dataset.layer==='map').disabled,true);
        assert.equal(inputs.find(input=>input.dataset.layer==='radar').disabled,false);
        assert.equal(inputs.find(input=>input.dataset.layer==='truth_targets'),undefined);
        assert.ok(!panel.enabled('truth_targets'));
      }
    }
    await new Promise(resolve=>setImmediate(resolve));
  }finally{globalThis.document=oldDocument;globalThis.window=oldWindow;}
});
