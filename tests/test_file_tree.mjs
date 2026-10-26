import test from 'node:test';
import assert from 'node:assert/strict';
import {fileTreeRows} from '../web/file-tree.js';

test('shared directories appear once with tree-compatible continuation guides',()=>{
  const rows=fileTreeRows(['weapons/predictor.py','perception/filter.py','main.py','weapons/control.py']);
  assert.deepEqual(rows.map(row=>row.prefix+row.name+(row.directory?'/':'')),[
    '├── perception/','│   └── filter.py','├── weapons/','│   ├── control.py','│   └── predictor.py','└── main.py'
  ]);
});

test('task highlights use complete paths, support multiple files and preserve reused files',()=>{
  const rows=fileTreeRows(['old/filter.py','new/filter.py','weapons/aim.py'],['new/filter.py','weapons/aim.py']);
  assert.deepEqual(rows.filter(row=>row.highlight).map(row=>row.path),['new/filter.py','weapons/aim.py']);
  assert.ok(rows.some(row=>row.path==='old/filter.py'&&!row.highlight));
});

test('nested directories, empty workspaces and input order remain deterministic',()=>{
  const paths=['a/nested/item.py','z.json','a/first.py'];
  assert.deepEqual(fileTreeRows(paths),fileTreeRows([...paths].reverse()));
  assert.deepEqual(fileTreeRows([]),[]);
  assert.equal(fileTreeRows(paths).find(row=>row.path==='a/nested/item.py').depth,3);
});
