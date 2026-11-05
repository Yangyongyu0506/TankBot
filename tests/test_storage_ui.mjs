import test from 'node:test';
import assert from 'node:assert/strict';
import {storageSummary} from '../web/storage-ui.js';
test('storage keeps current history archives backups and recovery accounting distinct',()=>{
  const rows=storageSummary({categories:{current:{count:1,bytes:5},history:{count:3,bytes:20},archives:{count:1,bytes:3},backups:{count:1,bytes:7},recovery:{count:2,bytes:13}}});
  assert.equal(rows.length,5);assert.equal(rows.reduce((n,r)=>n+r.bytes,0),48);
  assert.equal(rows.find(r=>r.key==='history').name,'历史版本');
  assert.equal(rows.find(r=>r.key==='recovery').bytes,13);
});
