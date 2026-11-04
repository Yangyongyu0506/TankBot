import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {levelGraph,levelState,newlyUnlocked} from '../web/level-tree.js';

const config=JSON.parse(readFileSync(new URL('../core/tests/fixtures/default-profile.json',import.meta.url)));
const catalogue=Object.entries(config.campaign.levels).map(([level_id,level])=>({level_id,title:level.title,chapter_id:level.chapter_id,...level.metadata}));
const graph=()=>levelGraph(catalogue,config.campaign.chapters);
const progress=(completed,unlocked,developer_mode=false)=>({completed_levels:completed,unlocked_levels:unlocked,developer_mode});

test('one public root and two lanes reflect all declared prerequisite edges',()=>{
  const g=graph();assert.deepEqual(g.roots.map(l=>l.level_id),['c0']);
  assert.deepEqual(g.lanes.map(l=>l.id),['weapons','navigation']);
  assert.deepEqual(g.edges.filter(e=>e.from==='c0'),[{from:'c0',to:'c1'},{from:'c0',to:'navigation.c0'}]);
  assert.equal(g.edges.length,8);assert.equal(g.depths.get('navigation.c2'),3);assert.equal(g.depths.get('c5'),5);
});

test('availability comes from authoritative progress, with independent completed/current badges',()=>{
  const g=graph(),p=progress(['c0'],['c0','c1','navigation.c0']);
  assert.deepEqual(levelState(g.byId.get('c0'),p,'c0'),{status:'completed',current:true,missing:[]});
  for(const id of ['c1','navigation.c0'])assert.equal(levelState(g.byId.get(id),p,'c0').status,'available');
  assert.deepEqual(levelState(g.byId.get('c4'),p,'c0'),{status:'locked',current:false,missing:['c3']});
  const nav=progress(['c0','navigation.c0','navigation.c1'],['c0','c1','navigation.c0','navigation.c1','navigation.c2']);
  assert.equal(levelState(g.byId.get('navigation.c2'),nav,'navigation.c1').status,'available');
  assert.equal(levelState(g.byId.get('c2'),nav,'navigation.c1').status,'locked');
  const denied=progress(['c0'],['c0']);assert.equal(levelState(g.byId.get('c1'),denied,'c0').status,'locked');
});

test('a single completion announces every new branch without awarding on replay, practice or developer mode',()=>{
  const before=progress([],['c0']),after=progress(['c0'],['c0','c1','navigation.c0']);
  assert.deepEqual(newlyUnlocked(before,after,'c0'),['c1','navigation.c0']);
  assert.deepEqual(newlyUnlocked(after,after,'c0'),[]);
  assert.deepEqual(newlyUnlocked(before,after,'c0',{practice:true}),[]);
  assert.deepEqual(newlyUnlocked(before,{...after,developer_mode:true},'c0'),[]);
  assert.deepEqual(newlyUnlocked(null,after,'c0'),[]);
});

test('layout is independent of catalogue order and particular level/chapter IDs',()=>{
  const g=levelGraph([
    {level_id:'finish',chapter_id:'second',order:0,prerequisites:['root']},
    {level_id:'root',chapter_id:'shared',order:3,prerequisites:[]},
    {level_id:'other',chapter_id:'first',order:2,prerequisites:['root']},
    {level_id:'join',chapter_id:'second',order:1,prerequisites:['finish','other']},
  ],[{chapter_id:'second',title:'Second'},{chapter_id:'first',title:'First'}]);
  assert.deepEqual(g.roots.map(l=>l.level_id),['root']);assert.equal(g.depths.get('join'),2);
  assert.equal(g.edges.length,4);assert.equal(g.lanes[0].title,'Second');
  assert.deepEqual(levelState(g.byId.get('join'),progress(['root','finish'],['root','finish','other']),'root').missing,['other']);
});

test('unknown, duplicate and cyclic catalogue relationships fail explicitly',()=>{
  assert.throws(()=>levelGraph([{level_id:'a',prerequisites:['absent']}]),/未知/);
  assert.throws(()=>levelGraph([{level_id:'a'},{level_id:'a'}]),/重复/);
  assert.throws(()=>levelGraph([{level_id:'a',prerequisites:['b']},{level_id:'b',prerequisites:['a']}]),/循环/);
});

test('developer selection keeps missing player prerequisites visible without awarding completion',()=>{
  const g=graph(),state=levelState(g.byId.get('c5'),progress([],['c0'],true),'c0');
  assert.equal(state.status,'available');assert.deepEqual(state.missing,['c4']);assert.equal(state.current,false);
});
