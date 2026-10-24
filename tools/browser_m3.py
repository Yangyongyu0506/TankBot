#!/usr/bin/env python3
"""Exercise the actual editor and staging UI in Firefox; use a disposable --workspace-store."""
import argparse
import base64
import hashlib
from datetime import date
import json
from pathlib import Path
import time
from browser_driver import Browser


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8765/?runtime=browser')
    parser.add_argument('--output',type=Path,default=Path('docs/reports/m3-browser.json'))
    parser.add_argument('--inspect',action='store_true')
    args=parser.parse_args();b=Browser()
    def click(id):
        b.until("return document.getElementById('workspace-panel').dataset.busy==='false'&&!document.getElementById("+json.dumps(id)+").disabled;")
        b.script(f"document.getElementById({json.dumps(id)}).click();return true;")
    def state(): return b.script("return JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');")
    def wait_last(kind,previous=None):
        value=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last&&s.last.kind==="+json.dumps(kind)+"&&s.last.id!=="+json.dumps(previous)+"&&s;",timeout=60)
        return value
    def edit(source):
        b.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        b.until("return !document.getElementById('save-workspace').disabled;")
    def choose(path):
        b.script("[...document.querySelectorAll('#file-list button')].find(e=>e.title==="+json.dumps(path)+").click();return true;")
    try:
        b.navigate(args.url)
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
        b.until("return document.getElementById('workspace-panel').dataset.deployment;")
        if args.inspect:
            print(b.script("return document.body.innerText;"));return
        click('open-workspace')
        # First test + deployment through real UI, including multi-file imports and player tests.
        previous=state().get('last',{});previous=previous.get('id') if previous else None
        click('test-workspace');tested=wait_last('test',previous)
        assert tested['last']['status']=='Ready',tested
        assert tested['last']['unit_tests']>=1,tested
        click('deploy-workspace');deployed=wait_last('deploy')
        assert deployed['last']['status']=='Active',deployed
        first=deployed['active'];run=deployed['run_id']
        # Add a file and edit it; actual Active digest stays fixed through editing and tests.
        name='helper_m3_'+str(int(time.time()))+'.py'
        b.script("document.getElementById('new-file-path').value="+json.dumps(name)+";return true;");click('new-file')
        b.until("return document.getElementById('editor-path').textContent==="+json.dumps(name)+";")
        edit('VALUE = 42\n')
        assert state()['active']==first
        click('save-workspace');b.until("return document.getElementById('save-workspace').disabled&&document.getElementById('workspace-panel').dataset.busy==='false';")
        assert state()['active']==first
        old=state()['last']['id'];click('test-workspace');second_test=wait_last('test',old)
        assert second_test['last']['status']=='Ready',second_test
        assert second_test['active']==first
        click('deploy-workspace');second=wait_last('deploy',first['deployment_id'])
        assert second['active']['sha256']==second_test['last']['sha256']
        assert second['active']['sha256']!=first['sha256']
        # Vim focus must not drive the chassis, turret or fire a shot.
        choose(name);click('vim-mode')
        before_focus=b.script("return {tick:Number(document.getElementById('tick').textContent),pose:['x','y','yaw'].map(id=>document.getElementById(id).textContent),turret:document.getElementById('turret').textContent,weapon:document.getElementById('weapon').textContent};")
        b.script("const e=document.querySelector('.cm-content');e.focus();for(const code of ['KeyW','KeyJ','KeyL','Space']){e.dispatchEvent(new KeyboardEvent('keydown',{code,key:code==='Space'?' ':code.slice(-1).toLowerCase(),bubbles:true}));e.dispatchEvent(new KeyboardEvent('keyup',{code,bubbles:true}));}return true;")
        assert not b.script("return Boolean(document.querySelector('button[data-key].active'));"), 'editor triggered controls'
        b.until("return Number(document.getElementById('tick').textContent)>="+str(before_focus['tick']+12)+";")
        after_focus=b.script("return {pose:['x','y','yaw'].map(id=>document.getElementById(id).textContent),turret:document.getElementById('turret').textContent,weapon:document.getElementById('weapon').textContent};")
        assert all(after_focus[k]==before_focus[k] for k in after_focus),(before_focus,after_focus)
        click('vim-mode')
        # Template plan preserves every existing file unless explicitly chosen.
        click('template-workspace');b.until("return !document.getElementById('migration-panel').hidden;")
        assert b.script("return [...document.querySelectorAll('#migration-list select')].every(e=>e.value==='keep');")
        click('cancel-migration')
        # Syntax errors are located by file/line and cannot replace Active.
        edit('def broken(:\n');click('test-workspace')
        b.until("return /invalid syntax|SyntaxError/.test(document.getElementById('workspace-message').textContent);")
        assert state()['active']['sha256']==second['active']['sha256']
        # Runtime startup failure leaves the active instance alive.
        edit('raise RuntimeError("M3 staging fixture")\n')
        # Only the entry module is imported at startup, so add a failing unit test instead.
        edit('VALUE = 42\n');click('save-workspace');b.until("return document.getElementById('save-workspace').disabled&&document.getElementById('workspace-panel').dataset.busy==='false';")
        choose('tests/test_project.py')
        edit('import unittest\nclass Failure(unittest.TestCase):\n def test_failure(self): self.fail("M3 fixture")\n')
        old=state()['last']['id'];click('test-workspace');failed=wait_last('test',old)
        assert failed['last']['status']=='Failed',failed
        assert failed['active']['sha256']==second['active']['sha256']
        # Explicit rollback uses old immutable files despite currently broken draft tests.
        b.script("document.getElementById('deployment-history').value="+json.dumps(first['sha256'])+";return true;")
        click('rollback-workspace');rolled=wait_last('rollback')
        assert rolled['active']['sha256']==first['sha256'],rolled
        assert rolled['active']['deployment_id']!=first['deployment_id']
        assert rolled['run_id']==run and rolled['tick']>deployed['tick']
        # Keep the disposable draft usable for reinspection and verify persistent reload.
        edit('import unittest\nclass ProjectTest(unittest.TestCase):\n def test_import(self):\n  from localization.kinematics import body_increment\n  self.assertTrue(callable(body_increment))\n')
        click('save-workspace');b.until("return document.getElementById('save-workspace').disabled&&document.getElementById('workspace-panel').dataset.busy==='false';")
        revision=b.script("return document.getElementById('workspace-panel').dataset.revision;")
        assert b.script("return document.getElementById('workspace-dialog').open&&document.scrollingElement.scrollTop===0;")
        shot=b.call('WebDriver:TakeScreenshot',{})['value']
        path=Path('.m1-cache')/(args.output.stem+'.png');path.write_bytes(base64.b64decode(shot))
        b.navigate(args.url);b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
        assert b.script("return Boolean([...document.querySelectorAll('#file-list button')].find(e=>e.title==="+json.dumps(name)+"));")
        b.script("window.__m3Archive=null;fetch('/api/workspace').then(r=>r.json()).then(w=>fetch('/api/workspace/archives',{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':w.control_token},body:'{}'})).then(r=>r.json()).then(records=>window.__m3Archive=records);return true;")
        archives=b.until("return window.__m3Archive; ")
        assert len(archives)>=4,archives
        capabilities=b.capabilities['capabilities']
        report={'date':date.today().isoformat(),'url':args.url,'browser':{k:capabilities[k] for k in ('browserName','browserVersion','platformName')},
                'tested':tested['last'],'first_deployment':first,'second_deployment':second['active'],'failed_test':failed['last'],'rollback':rolled['active'],
                'run_unchanged':rolled['run_id']==run,'world_ticks_advanced':rolled['tick']-deployed['tick'],
                'edit_preserves_active':True,'vim_focus_isolated':True,'template_defaults_keep':True,'syntax_diagnostic':True,'persistent_file':name,'revision':revision,'screenshot':str(path),'archived_records':len(archives)}
        root=Path(__file__).resolve().parents[1]
        paths=['config/game.yaml','package-lock.json','build/web/editor-bundle.js','build/browser/authority-bundle.json','build/browser/player-bundle.json','target/wasm32-unknown-unknown/release/tankbot_core.wasm']
        report['artifacts']={p:{'bytes':(root/p).stat().st_size,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in paths}
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(args.output)
    finally:b.close()


if __name__=='__main__':main()
