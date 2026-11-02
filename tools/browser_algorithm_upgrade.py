#!/usr/bin/env python3
"""Real editor regression for an untouched old polar algorithm with a current adapter."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-store',type=Path)
    parser.add_argument('--url');parser.add_argument('--port',type=int,default=2836)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.prepare_store:
        from test_template_stub_upgrade import GeneratedAlgorithmUpgradeTests
        if (args.prepare_store/'HEAD.json').exists():raise SystemExit('Use a fresh disposable store')
        api,_=GeneratedAlgorithmUpgradeTests().project(args.prepare_store,'c3')
        current=api.store.read();api.store.edit(current['revision'],{
            'perception/transforms.py':'# authored C1 code: preserve\n',
            'perception/tracker.py':'# authored C2 code: preserve\n'})
        return
    b=Browser(args.port)
    def workspace():
        b.script("window.__stubWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__stubWorkspace=v);return true;")
        return b.until('return window.__stubWorkspace;')
    def click(name):
        b.until("return document.getElementById('workspace-panel').dataset.busy==='false'&&!document.getElementById("+json.dumps(name)+").disabled;")
        b.script('document.getElementById('+json.dumps(name)+').click();return true;')
    try:
        b.navigate(args.url);b.call('WebDriver:SetWindowRect',{'width':1440,'height':950})
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
        before=workspace();assert before['learning']['upgrade_required']
        assert before['learning']['upgrade']['generated_algorithm_files']==['perception/polar_tracker.py']
        click('open-workspace');click('test-workspace')
        b.until("return !document.getElementById('migration-panel').hidden;")
        summaries=b.script("return [...document.querySelectorAll('#migration-list summary')].map(n=>n.textContent);")
        assert any('perception/polar_tracker.py' in s and '旧算法空模板' in s for s in summaries),summaries
        assert not any(s.startswith(('perception/tracker.py','perception/transforms.py')) for s in summaries)
        assert workspace()['snapshot']['revision']==before['snapshot']['revision']
        click('upgrade-and-test')
        b.until("const root=document.getElementById('workspace-panel'),s=JSON.parse(root.dataset.deployment||'{}');return s.reports?.some(r=>r.status==='Ready'&&r.revision===root.dataset.revision);",90)
        after=workspace();assert not after['learning']['upgrade_required']
        code=after['snapshot']['files']['perception/polar_tracker.py']
        assert 'measurements: tuple[PolarTargetEstimate, ...]' in code
        for path in ('perception/transforms.py','perception/tracker.py'):
            assert after['snapshot']['files'][path]==before['snapshot']['files'][path]
        assert not b.script("return document.getElementById('deploy-workspace').disabled;")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        shot=args.output.with_suffix('.png');shot.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']))
        args.output.write_text(json.dumps({'url':args.url,'old_revision':before['snapshot']['revision'],'new_revision':after['snapshot']['revision'],
            'tuple_signature':True,'explicit_preview':True,'authored_algorithms_preserved':True,'test_ready':True,'screenshot':str(shot)},indent=2)+'\n')
        print('PASS: old generated ndarray stub -> explicit preview -> tuple signature; C1/C2 preserved; Ready')
    finally:b.close()


if __name__=='__main__':main()
