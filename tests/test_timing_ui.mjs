import test from 'node:test';
import assert from 'node:assert/strict';
import {timingRows} from '../web/timing-ui.js';
test('timing shows measured phases and p99 without filling unavailable metrics with zero',()=>{
  const rows=timingRows({costs:{round_trip_ms:{count:2,p50_ms:1,p95_ms:2,p99_ms:2},worker_encode_previous_ms:{count:1,p50_ms:.1,p95_ms:.1,p99_ms:.1},worker_decode_ms:{count:0,p99_ms:null}}});
  assert.equal(rows.length,2);assert.equal(rows[0].p99_ms,2);assert.match(rows[1].name,/前批/);
  assert.deepEqual(timingRows(null),[]);
});
