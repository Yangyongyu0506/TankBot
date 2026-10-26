import test from 'node:test';
import assert from 'node:assert/strict';
import {polarHits,drawRadar} from '../web/campaign-ui.js';

test('armor display uses only current anonymous polar rows, including one/zero observations',()=>{
  const message={schema:'armor_detections@1',payload:{measurements_rt:[[2.,0.],[3.,Math.PI/2]]}};
  assert.deepEqual(polarHits(message),[{range_m:2,bearing_rad:0},{range_m:3,bearing_rad:Math.PI/2}]);
  assert.deepEqual(polarHits({schema:'armor_detections@1',payload:{measurements_rt:[]}}),[]);
  const calls=[],ctx=new Proxy({}, {get:(_,name)=>(...args)=>calls.push([name,...args]),set:()=>true});
  const canvas={width:240,height:190,getContext:()=>ctx};
  drawRadar(canvas,message,12);
  const points=calls.filter(call=>call[0]==='arc'&&call[3]===3);
  assert.equal(points.length,2);
  assert.equal(points[0][1],120);assert.ok(points[0][2]<95);
  assert.ok(points[1][1]<120);assert.equal(points[1][2],95);
  assert.deepEqual(message.payload.measurements_rt,[[2.,0.],[3.,Math.PI/2]]);
});

test('existing center Radar retains its existing representation',()=>{
  const detections=[{observation_id:'local',range_m:4,bearing_rad:.3}];
  assert.equal(polarHits({schema:'radar@1',payload:{detections}}),detections);
});
