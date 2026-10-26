import test from 'node:test';
import assert from 'node:assert/strict';
import {referenceType,symbolHelp,sdkCompletions} from '../web/sdk-hints.js';

const reference={lesson:{aliases:{own_pose:'Pose2D'}},types:[
  {name:'Pose2D',description:'自身地图位姿',fields:[{name:'x_m',type:'float',description:'横坐标，单位 m'},{name:'yaw_rad',type:'float',description:'逆时针角，单位 rad'}],methods:[]},
  {name:'TargetEstimate',description:'目标估计',fields:[{name:'x_m',type:'float',description:'地图横坐标'}],methods:[]},
  {name:'ndarray',description:'NumPy 数组',fields:[{name:'shape',type:'tuple[int, ...]',description:'数组形状'}],methods:[]},
]};
test('help resolves actual annotations and older lesson parameters',()=>{
  assert.equal(referenceType(reference,'own_pose','').name,'Pose2D');
  assert.equal(referenceType(reference,'point','point: TargetEstimate = value').name,'TargetEstimate');
  assert.equal(referenceType(reference,'T','T: NDArray[np.float64] = np.eye(4)').name,'ndarray');
  assert.equal(symbolHelp(reference,'own_pose.yaw_rad','').description,'逆时针角，单位 rad');
});
test('member completion offers declared fields and leaves unknown objects alone',()=>{
  const text='def f(own_pose: Pose2D):\n    own_pose.';
  assert.deepEqual(sdkCompletions(reference,text,text.length).options.map(item=>item.label),['x_m','yaw_rad']);
  assert.equal(sdkCompletions(reference,'unknown.',8),null);
  assert.equal(symbolHelp(reference,'own_pose.hidden_truth',''),null);
});
test('computed read-only polar properties are documented and completed without becoming constructor fields',()=>{
  const updated={lesson:{},types:[{name:'AimInput',description:'控制输入',fields:[],methods:[],properties:[{name:'target_rt',type:'NDArray[np.float64] | None',description:'车体系 [r,theta]'}]}]};
  const source='observation: AimInput\nobservation.';
  assert.equal(sdkCompletions(updated,source,source.length).options[0].label,'target_rt');
  assert.equal(symbolHelp(updated,'observation.target_rt',source).description,'车体系 [r,theta]');
  assert.deepEqual(updated.types[0].fields,[]);
});
