#!/usr/bin/env python3
"""Disposable real-UI Navigation edit/test/deploy and cross-chapter regression."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--port',type=int,default=2838)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from navigation_support import solution
    code=solution(configure(load_config(ROOT/'config/game.yaml'),'navigation.c0'))['control/wheel_controller.py']
    b=Browser(args.port);evidence={'url':args.url}
    def ready():b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
    def click(name):
        b.until("return !document.getElementById("+json.dumps(name)+").disabled;")
        b.script('document.getElementById('+json.dumps(name)+').click();return true;')
    def workspace():
        b.script("window.__navWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__navWorkspace=v);return true;")
        return b.until('return window.__navWorkspace;')
    def switch(level):
        origin=b.script('return performance.timeOrigin;')
        b.script("document.getElementById('level-select').value="+json.dumps(level)+";return true;")
        click('start-level');b.until('return performance.timeOrigin!=='+str(origin)+';');ready()
    def status():
        b.script("window.__navAttempt=null;(async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__navAttempt=q?JSON.parse(await q.post('/api/campaign',{})).value:await(await fetch('/api/campaign')).json();})();return true;")
        return b.until('return window.__navAttempt;')
    def shot(suffix):
        path=args.output.with_name(args.output.stem+'-'+suffix+'.png')
        path.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']))
        return str(path.resolve().relative_to(ROOT))
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        b.navigate(args.url);b.call('WebDriver:SetWindowRect',{'width':1440,'height':950});ready()
        if workspace()['level_id']!='c2':switch('c2')
        original=workspace()
        switch('navigation.c0');nav=workspace()
        assert set(nav['snapshot']['files'])=={'navigation_robot.py','control/__init__.py','control/wheel_controller.py','tankbot.json','contracts/wheel_control.json'}
        assert b.script("return document.getElementById('tab-weapons').hidden;")
        click('open-workspace')
        assert b.script("return document.querySelector('#file-list .task-file').title==='control/wheel_controller.py';")
        b.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(code)+");return true;")
        if not b.script("return document.getElementById('save-workspace').disabled;"):
            click('save-workspace')
        b.until("return document.getElementById('workspace-panel').dataset.dirty==='false'&&document.getElementById('workspace-panel').dataset.busy==='false';")
        click('test-workspace')
        report=b.until("const p=document.getElementById('workspace-panel'),s=JSON.parse(p.dataset.deployment||'{}');return !s.job&&s.reports?.find(r=>r.revision===p.dataset.revision&&r.status==='Ready');",120)
        assert status()['attempt']['phase']=='preparing'
        evidence['editor_screenshot']=shot('editor');evidence['report']=report
        click('deploy-workspace')
        b.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;",120)
        b.until("return document.getElementById('campaign-summary').dataset.phase==='running';")
        evidence['running_screenshot']=shot('running')
        b.until("return document.getElementById('task-status').dataset.status==='passed';",90)
        b.until("return Number(document.getElementById('arena').dataset.trailPoints)>10;")
        ended=status();evidence['attempt']=ended['attempt'];evidence['result_screenshot']=shot('result')
        result=ended['attempt']['result'];assert result['origin_distance_m']<=.30 and result['path_length_m']>=7.2,result
        before_retry=workspace();switch('navigation.c0');after_retry=workspace()
        assert before_retry['snapshot']['files']==after_retry['snapshot']['files']
        retried=status();assert retried['run_id']!=ended['run_id'] and retried['attempt']['phase']=='preparing'
        switch('c2');restored=workspace()
        assert restored['snapshot']==original['snapshot'],'Weapons source or history changed'
        switch('navigation.c0');assert workspace()['snapshot']==after_retry['snapshot']
        assert b.script('return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;')
        evidence.update(independent_workspace=True,weapons_unchanged=True,retry_preserved_source=True,editor_closed_on_deploy=True)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: Navigation real Test/Deploy/square completion, weapon removal, retry and unchanged Weapons source/history')
    finally:b.close()


if __name__=='__main__':main()
