import test from 'node:test';
import assert from 'node:assert/strict';
import {groupLogEntries,sourceLocation} from '../web/runtime-logs.js';

test('a Python traceback stays contiguous across log lines, chunks and received ticks',()=>{
  const identity={source:'test',module_id:'perception',deployment_id:'one',revision:'snapshot',stream:'output'};
  const texts=['Traceback (most recent call last):\n','  File "perception/tracker.py", line 50, in update\n','    return H\n',"NameError: name 'H' is not defined\n"];
  const entries=texts.map((text,tick)=>({...identity,text,tick}));
  const groups=groupLogEntries(entries);
  assert.equal(groups.length,1);
  assert.equal(groups[0].text,texts.join(''));
  assert.equal(groups[0].tick,0);assert.equal(groups[0].lastTick,3);
  assert.equal(entries[0].text,texts[0]);
});

test('different candidate versions, streams and sources keep their own log blocks',()=>{
  const entry={source:'test',module_id:'perception',deployment_id:'one',revision:'snapshot',stream:'output',text:'one\n'};
  for(const [field,value] of [['source','runtime'],['module_id','tracking'],['deployment_id','two'],['revision','next'],['stream','error']]){
    assert.equal(groupLogEntries([entry,{...entry,[field]:value}]).length,2,field);
  }
});

test('Python and syntax error locations link to project files with exact line numbers',()=>{
  assert.deepEqual(sourceLocation('  File "perception/tracker.py", line 50, in update'),{path:'perception/tracker.py',line:50});
  assert.deepEqual(sourceLocation('tests/test_model.py:12: failed'),{path:'tests/test_model.py',line:12});
  for(const text of ['  File "runtime/module_runner.py", line 63','  File "/etc/secret.py", line 1','  File "../other.py", line 1','plain output'])assert.equal(sourceLocation(text),null);
});
