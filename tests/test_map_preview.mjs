import test from 'node:test';
import assert from 'node:assert/strict';
import {mapBounds,mapProjection,drawMapPreview} from '../web/map-preview.js';
test('bounds include full wall extent and equal scale preserves world axes',()=>{
  const bounds=mapBounds([{center:[10,4],size:[20,8]}]);
  assert.deepEqual(bounds,{minX:0,minY:0,maxX:20,maxY:8,width:20,height:8});
  const {point,scale}=mapProjection(bounds,1000,600);
  assert.deepEqual(point(10,4),[500,300]);
  assert.equal(point(11,4)[0]-500,scale);assert.equal(300-point(10,5)[1],scale);
  for(const [x,y] of [[0,0],[20,8]]){const [px,py]=point(x,y);assert.ok(px>=40&&px<=960&&py>=40&&py<=560);}
  assert.equal(mapBounds([]),null);
});
test('preview draws only supplied walls and handles hidden or empty maps',()=>{
  const calls=[];const ctx=new Proxy({}, {get:(_,key)=>(...args)=>calls.push([key,...args]),set:()=>true});
  const canvas={width:1000,height:600,getContext:()=>ctx};
  drawMapPreview(canvas,{walls:[{center:[0,0],size:[24,18]},{center:[2,3],size:[1,2]}]});
  assert.equal(calls.filter(c=>c[0]==='strokeRect').length,2);
  calls.length=0;drawMapPreview(canvas,null);assert.equal(calls.filter(c=>c[0]==='strokeRect').length,0);
  assert.ok(calls.some(c=>c[0]==='fillText'&&c[1].includes('未授权')));
  calls.length=0;drawMapPreview(canvas,{walls:[]});assert.ok(calls.some(c=>c[0]==='fillText'&&c[1].includes('无静态墙体')));
});
