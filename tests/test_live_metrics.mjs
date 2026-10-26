import test from 'node:test';
import assert from 'node:assert/strict';
import {MetricHistory} from '../web/live-metrics.js';

const settings={metric:'rmse_m',label:'累计位置 RMSE',unit:'m',precision:3,history_points:3};
const attempt=(value,count)=>({live_metrics:{rmse_m:value,scored_samples:count}});

test('empty or invalid statistics are not shown as zero error',()=>{
  const history=new MetricHistory(settings);
  for(const value of [undefined,null,NaN,Infinity,-1,'0'])history.update('run',attempt(value,1));
  assert.equal(history.latest,null);assert.equal(history.summary,'');assert.equal(history.polyline,'');
  history.update('run',attempt(0,1));
  assert.equal(history.summary,'累计位置 RMSE 0.000 m');assert.ok(!history.polyline.includes('NaN'));
});

test('polls do not duplicate samples, history stays bounded and old reports do not rewind it',()=>{
  const history=new MetricHistory(settings);
  history.update('run',attempt(4,1));history.update('run',attempt(4,1));
  assert.equal(history.points.length,1);
  for(let n=2;n<=100;n++)history.update('run',attempt(1/n,n));
  assert.equal(history.points.length,settings.history_points);
  history.update('run',attempt(99,3));assert.equal(history.latest.samples,100);
  assert.equal(history.summary,'累计位置 RMSE 0.010 m');assert.ok(!/NaN|Infinity/.test(history.polyline));
});

test('a new run clears the displayed value and graph while deployment within a run does not',()=>{
  const history=new MetricHistory(settings);
  history.update('old',attempt(.5,4));history.update('old',attempt(.4,6));assert.equal(history.points.length,2);
  history.update('new',attempt(null,0));assert.equal(history.summary,'');assert.equal(history.points.length,0);
  history.update('new',attempt(.2,1));assert.equal(history.latest.samples,1);
});
