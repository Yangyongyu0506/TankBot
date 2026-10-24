#!/usr/bin/env python3
"""UI regression: legacy teaching framework -> explicit preview -> Ready -> deploy."""
import argparse
import base64
from datetime import date
import hashlib
import json
import yaml
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-store',type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:8775')
    parser.add_argument('--browser-port',type=int,default=2829)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/reports/teaching-upgrade-native.json')
    args=parser.parse_args()
    if args.prepare_store:
        sys.path[:0]=[str(ROOT/name) for name in ('host','protocol','sdk/python','tests')]
        from tankbot_host.campaign import configure
        from tankbot_host.workspace import WorkspaceStore
        from campaign_support import solutions
        config=configure(yaml.safe_load((ROOT/'config/game.yaml').read_text()),'c1')
        if (args.prepare_store/'HEAD.json').exists():raise SystemExit('Use a new disposable store')
        files=solutions(config)
        files['campaign_robot.py']='# old unversioned framework\n'
        files['perception/coordinates.py']='# historical algorithm; preserve exactly\n'
        files['tests/test_player_custom.py']='import unittest\nclass PlayerTest(unittest.TestCase):\n    def test_example(self) -> None:\n        self.assertEqual(1 + 1, 2)\n'
        snapshot=WorkspaceStore(args.prepare_store,files,config['workspace']).read()
        print(snapshot['revision']);return
    b=Browser(args.browser_port)
    def click(identifier):
        b.until('return document.getElementById("workspace-panel").dataset.busy==="false"&&!document.getElementById('+json.dumps(identifier)+').disabled;')
        b.script('document.getElementById('+json.dumps(identifier)+').click();return true;')
    def workspace():
        b.script("window.__upgradeWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__upgradeWorkspace=v);return true;")
        return b.until('return window.__upgradeWorkspace;')
    def edit(source):
        b.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
    def screenshot(suffix):
        path=ROOT/'.m1-cache'/(args.output.stem+'-'+suffix+'.png')
        path.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']))
        return path.relative_to(ROOT).as_posix()
    try:
        b.navigate(args.url);b.call('WebDriver:SetWindowRect',{'width':1440,'height':900})
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
        original=workspace();assert original['learning']['upgrade_required']
        click('open-workspace')
        if not b.script("return document.getElementById('learning-pane').hidden;"):click('close-learning')
        assert b.script("return !document.getElementById('workspace-upgrade').hidden&&document.getElementById('deploy-workspace').disabled;")
        assert '测试' in b.script("return document.getElementById('test-workspace').title;")
        source=original['snapshot']['files']['perception/transforms.py']+'\n# Keep this unsaved algorithm edit.\n'
        edit(source);b.until("return !document.getElementById('save-workspace').disabled;")
        click('test-workspace');b.until("return !document.getElementById('migration-panel').hidden;")
        expected={'campaign_robot.py','tankbot.json','contracts/perception.json','tests/test_coordinates.py'}
        listed=b.script("return [...document.querySelectorAll('#migration-list summary')].map(n=>n.textContent.split(' · ')[0]);")
        assert set(listed)==expected,listed
        assert b.script("return !document.getElementById('upgrade-and-test').hidden&&document.getElementById('deploy-workspace').disabled;")
        preview=screenshot('preview')
        click('cancel-migration')
        saved=workspace();assert saved['snapshot']['files']['perception/transforms.py']==source
        assert saved['snapshot']['files']['campaign_robot.py']==original['snapshot']['files']['campaign_robot.py']
        click('test-workspace');b.until("return !document.getElementById('migration-panel').hidden;")
        click('upgrade-and-test')
        report=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s.last;",timeout=90)
        assert report['status']=='Ready',report
        b.until("return !document.getElementById('deploy-workspace').disabled;")
        after=workspace();assert not after['learning']['upgrade_required']
        for path,text in saved['snapshot']['files'].items():
            if path not in expected:assert after['snapshot']['files'][path]==text,path
        assert b.script("return document.getElementById('workspace-upgrade').hidden&&document.querySelectorAll('.learning-upgrade').length===0;")
        assert '测试通过' in b.script("return document.getElementById('deploy-help').textContent;")
        ready=screenshot('ready')
        # The report is tied to the tested snapshot: editing must disable deployment again.
        edit(source+'# Another draft change.\n')
        b.until("return document.getElementById('deploy-workspace').disabled&&document.getElementById('deploy-help').textContent.includes('未保存');")
        edit(source);b.until("return !document.getElementById('deploy-workspace').disabled;")
        click('deploy-workspace')
        active=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.status==='Active'&&s.active;",timeout=90)
        click('close-workspace')
        b.until("return document.getElementById('arena').dataset.targetEstimateX!=='';")
        result={'date':date.today().isoformat(),'url':args.url,'browser':b.capabilities['capabilities']['browserVersion'],
                'preview_only_managed_files':listed,'cancel_preserves_saved_algorithm':True,'algorithm_files_preserved':True,
                'upgrade_notice_cleared':True,'edit_disables_deployment':True,'test':report,'active':active,
                'screenshots':[preview,ready]}
        paths=('web/workspace-ui.js','web/learning-ui.js','web/index.html','web/style.css','host/tankbot_host/campaign_templates.py',
               'host/tankbot_host/workspace_api.py','host/tankbot_host/deployment.py','host/tankbot_host/learning.py','tools/browser_template_upgrade.py')
        result['sources']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(args.output)
    finally:b.close()


if __name__=='__main__':main()
