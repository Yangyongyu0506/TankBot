import test from 'node:test';
import assert from 'node:assert/strict';
import {ControlHistory} from '../web/control-feedback.js';

const chart={signals:[{signal:'command_vx_mps',color:'#f4cf7e'},{signal:'encoder_vx_mps',color:'#8fe3b5'}]};
const config={history_points:3,charts:[chart]};
const point=(tick,value,segment=0)=>({simulation_tick:tick+12,elapsed_ticks:tick,cycle_index:0,segment_index:segment,label:segment?'转向':'直行',values:{command_vx_mps:segment?0:.5,encoder_vx_mps:value,truth_x:999}});
const attempt=points=>({control_feedback:{points}});

test('control curves retain full Authority samples across slow polls and discard undeclared values',()=>{
  const h=new ControlHistory(config);h.update('a',attempt([point(0,0),point(6,.3),point(12,.5)]));
  assert.equal(h.points.length,3);assert.equal(h.points[0].values.truth_x,undefined);
  h.update('a',attempt([point(0,0),point(6,.3),point(12,.5)]));assert.equal(h.points.length,3);
  h.update('a',attempt([point(0,0),point(6,.3),point(12,.5),point(18,-.1,1)]));
  assert.equal(h.points.length,3);assert.equal(h.points[0].elapsed_ticks,6);
  h.update('a',attempt([point(6,99)]));assert.equal(h.points.at(-1).values.encoder_vx_mps,-.1);
});

test('signed feedback, step commands and phase transitions have finite plot coordinates',()=>{
  const h=new ControlHistory(config);h.update('a',attempt([point(0,0),point(6,.5),point(12,-.2,1)]));
  const g=h.geometry(chart,24);
  assert.ok(g.min<-.2);assert.ok(g.max>.5);
  assert.ok(g.lines[0].d.includes(' H '));assert.ok(g.lines[1].d.includes(' L '));
  assert.equal(g.markers.length,1);assert.equal(g.markers[0].label,'转向');
  assert.ok(!JSON.stringify(g).match(/NaN|Infinity/));
});

test('cursor deltas append without losing earlier curves and a new epoch starts a fresh history',()=>{
  const h=new ControlHistory(config);h.update('a',attempt([point(0,0),point(6,.3)]));
  h.update('a',{control_feedback:{complete:false,points:[point(6,.3),point(12,.5)]}});
  assert.deepEqual(h.points.map(p=>p.elapsed_ticks),[0,6,12]);
  h.update('a',{control_feedback:{complete:false,points:[]}});assert.equal(h.points.length,3);
  h.update('b',{control_feedback:{complete:true,points:[point(0,0)]}});assert.equal(h.points.length,1);
});

test('empty or invalid samples are not shown as a successful zero-speed controller; retry clears history',()=>{
  const h=new ControlHistory(config);assert.equal(h.points.length,0);
  h.update('a',attempt([point(0,NaN)]));assert.equal(h.points[0].values.encoder_vx_mps,undefined);
  assert.ok(!h.geometry(chart,0).lines[1].d.includes('NaN'));
  h.update('a',attempt([point(6,.4)]));
  h.update('b',{});assert.equal(h.points.length,0);
});
