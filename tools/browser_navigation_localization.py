#!/usr/bin/env python3
"""Disposable Firefox C1 -> C2 upgrade, EKF edit/test/deploy and localization layers."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--port',type=int,default=2849)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from navigation_support import solution
    files=solution(configure(load_config(ROOT/'config/game.yaml'),'navigation.c2'))
    browser=Browser(args.port);evidence={'url':args.url}
    def ready():browser.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
    def click(name):
        browser.until('return !document.getElementById('+json.dumps(name)+').disabled;')
        browser.script('document.getElementById('+json.dumps(name)+').click();return true;')
    def workspace():
        browser.script("window.__ekfWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__ekfWorkspace=v);return true;")
        return browser.until('return window.__ekfWorkspace;')
    def request(endpoint):
        browser.script("window.__ekfResponse=null;(async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__ekfResponse=q?JSON.parse(await q."+
                       ("view()" if endpoint=='view' else "post('/api/campaign',{})")+
                       "):await(await fetch('/api/"+endpoint+"')).json();})();return true;")
        response=browser.until('return window.__ekfResponse;')
        return response.get('value',response) if endpoint=='campaign' else response
    def switch(level):
        origin=browser.script('return performance.timeOrigin;')
        browser.script("document.getElementById('level-select').value="+json.dumps(level)+';return true;')
        click('start-level');browser.until('return performance.timeOrigin!=='+str(origin)+';');ready()
    def shot(name):
        path=args.output.with_name(args.output.stem+'-'+name+'.png')
        path.write_bytes(base64.b64decode(browser.call('WebDriver:TakeScreenshot',{})['value']))
        return str(path.resolve().relative_to(ROOT))
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        browser.navigate(args.url);browser.call('WebDriver:SetWindowRect',{'width':1440,'height':950});ready()
        switch('navigation.c1')
        if workspace()['learning']['upgrade_required']:
            click('open-workspace');click('test-workspace')
            browser.until("return !document.getElementById('migration-panel').hidden;",90)
            click('upgrade-and-test')
            browser.until("return !document.getElementById('deploy-workspace').disabled;",120)
            click('close-workspace')
        before=workspace()['snapshot']['files']
        assert 'localization/odometry.py' in before,'Start this disposable service in Navigation C1 with a reference seed.'
        switch('navigation.c2')
        unlocked=workspace()
        for path in ('control/wheel_controller.py','localization/odometry.py'):
            assert unlocked['snapshot']['files'][path]==before[path]
        assert unlocked['learning']['upgrade_required']
        click('open-workspace')
        assert browser.script("return [...document.querySelectorAll('#file-list .task-file')].some(n=>n.title==='localization/ekf.py');")
        browser.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(files['localization/ekf.py'])+');return true;')
        if not browser.script("return document.getElementById('save-workspace').disabled;"):click('save-workspace')
        click('test-workspace')
        browser.until("return !document.getElementById('migration-panel').hidden;",90)
        listed=browser.script("return [...document.querySelectorAll('#migration-list summary')].map(n=>n.textContent.split(' · ')[0]);")
        assert not set(listed)&{'control/wheel_controller.py','localization/odometry.py','localization/ekf.py'},listed
        click('upgrade-and-test')
        browser.until("return !document.getElementById('deploy-workspace').disabled;",120)
        click('deploy-workspace')
        browser.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;",120)
        browser.until("return Number(document.querySelector('#live-evaluation>div').dataset.samples)>60;",45)
        current=request('view');assert current['schema']=='view_snapshot@5'
        assert current['payload']['selected_pose']['source_id']=='ekf'
        assert len(current['payload']['pose_estimates'])==2
        fix=next(m for m in current['payload']['local_observations'] if m['schema']=='position_fix2d@1')
        assert set(fix['payload'])=={'position_m','covariance'}
        assert current['payload']['selected_pose']['pose']['covariance'] is not None
        click('tab-visualization')
        layers=json.loads(browser.script("return document.getElementById('arena').dataset.visibleLayers;"))
        assert {'gps','pose_estimates','pose_covariance'}<=set(layers)
        assert not {'truth_robot','truth_targets','colliders','velocities'}&set(layers)
        evidence['running']=shot('running')
        assert browser.script("return [...document.querySelectorAll('#live-evaluation>div')].every(n=>Number(n.dataset.referenceSamples)>0&&n.querySelectorAll('polyline').length===2);")
        browser.until("return document.getElementById('task-status').dataset.status==='passed';",90)
        ended=request('campaign');evidence['result']=ended['attempt']['result'];assert evidence['result']['passed']
        evidence['finished']=shot('result')
        for path in ('control/wheel_controller.py','localization/odometry.py'):
            assert workspace()['snapshot']['files'][path]==before[path]
        revision=workspace()['snapshot']['revision'];switch('navigation.c2')
        assert workspace()['snapshot']['revision']==revision
        fresh=request('campaign');assert fresh['run_id']!=ended['run_id']
        assert fresh['attempt']['live_metrics']['rmse_m'] is None
        assert fresh['attempt']['live_metrics']['reference_rmse_m'] is None
        restarted_view=request('view')
        assert all(message['run_id']==fresh['run_id'] for message in restarted_view['payload']['pose_estimates'])
        assert browser.script('return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;')
        evidence.update(algorithms_preserved=True,managed_upgrade_only=True,editor_closed_and_locked=True,
                        gps_and_estimates_only=True,comparison_axes_shared=True,retry_clears_feedback=True)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: C2 GPS/EKF edit/test/deploy, preserved C1 sources, layers, RMSE comparison and retry')
    except BaseException:
        evidence['failure_screenshot']=shot('failure')
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        raise
    finally:browser.close()


if __name__=='__main__':main()
