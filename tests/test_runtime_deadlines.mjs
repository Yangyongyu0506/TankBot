import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function bridge(){
  let bind,now=0,serial=0;const timers=new Map(),events=[],workers=[];
  const parent={},port={postMessage:value=>events.push(value),start(){}};
  class Worker{
    constructor(){workers.push(this);this.terminated=false;}
    postMessage(value){this.last=value;}
    terminate(){this.terminated=true;}
    emit(value){this.onmessage({data:value});}
  }
  const context={window:{addEventListener:(name,fn)=>{bind=fn;}},parent,location:{search:'?ui=http%3A%2F%2Fui'},
    URLSearchParams,TextEncoder,Worker,performance:{now:()=>now},
    setTimeout:(fn,ms)=>{const id=++serial;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id)};
  vm.runInNewContext(readFileSync(new URL('../web/runtime-frame.js',import.meta.url),'utf8'),context);
  bind({source:parent,origin:'http://ui',data:'tankbot-runtime',ports:[port]});
  const send=(op,worker_id,value={})=>port.onmessage({data:JSON.stringify({op,worker_id,value})});
  function init(id){
    send('init',id,{init:{},limit:65536,budget_ms:20,batch_wall_deadline_ns:20_000_000,max_log_bytes:8192,startup_timeout_s:5});
    const w=workers.at(-1);w.emit({op:'ready',runtime_packages:{}});return w;
  }
  return {events,timers,send,init,now:value=>{now=value;}};
}

test('iframe explicitly checks arrival even when the wall timer callback is delayed',()=>{
  const b=bridge(),w=b.init('a');b.send('step','a',{});b.now(20.000001);
  w.emit({op:'result',raw:'{}'});
  assert.equal(w.terminated,true);
  assert.equal(b.events.at(-1).op,'fault');assert.equal(b.events.at(-1).location,'wall_deadline');
  assert.equal(b.events.some(e=>e.op==='result'),false);
});

test('exact expiry is accepted without epsilon and a callback at exact expiry rechecks',()=>{
  const b=bridge(),w=b.init('a');b.send('step','a',{});b.now(20);
  const timer=[...b.timers.values()][0];timer.fn();
  assert.equal(w.terminated,false);
  w.emit({op:'result',raw:'{}'});
  assert.equal(b.events.at(-1).op,'result');assert.equal(b.events.at(-1).elapsed_ms,20);
});

test('nonreturning workers terminate and old callbacks cannot enter a replacement lease',()=>{
  const b=bridge(),old=b.init('old');b.send('step','old',{});b.now(21);
  [...b.timers.values()][0].fn();assert.equal(old.terminated,true);
  const current=b.init('new'),count=b.events.length;
  old.emit({op:'result',raw:'{}'});assert.equal(b.events.length,count);
  b.send('step','new',{});b.now(22);current.emit({op:'result',raw:'{}'});
  assert.equal(b.events.at(-1).worker_id,'new');assert.equal(current.terminated,false);
  current.emit({op:'result',raw:'{}'});assert.equal(current.terminated,true);
  assert.equal(b.events.at(-1).code,'RESOURCE_LIMIT');
  b.send('close','new');assert.equal(b.timers.size,0);
});
