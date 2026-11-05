import test from 'node:test';
import assert from 'node:assert/strict';
import {curveGeometry,experimentComparison} from '../web/experiment-ui.js';

test('missing samples break measurement curves rather than inventing zero measurements',()=>{
  const points=[{tick:0,v:1},{tick:6,v:null},{tick:12,v:2}];
  const g=curveGeometry(points,p=>p.v);
  assert.equal((g.path.match(/M/g)||[]).length,2);
  assert.equal(g.minimum,1);assert.equal(g.maximum,2);
  assert.equal(curveGeometry(points,()=>null).path,'');
});
test('version identity, actual execution and missing scoring references remain explicit',()=>{
  const rows=experimentComparison([{revision:'one',status:'Completed',input_sha256:'shared',points:[{missing:true}],rmse_m:null,scored_samples:0,failure:null},
    {revision:'two',status:'Failed',input_sha256:'shared',points:[],rmse_m:null,scored_samples:0,failure:{tick:6}}]);
  assert.equal(rows[0].samples,0);assert.equal(rows[0].rmse,null);assert.equal(rows[0].executed,1);
  assert.equal(rows[0].input,rows[1].input);assert.equal(rows[1].failure.tick,6);
});
