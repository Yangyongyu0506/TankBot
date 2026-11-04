#!/usr/bin/env python3
"""Disposable player C2 -> C3 upgrade, waypoint editing and real native/browser completion."""
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
    parser.add_argument('--port',type=int,default=2861)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from navigation_support import solution
    files=solution(configure(load_config(ROOT/'config/game.yaml'),'navigation.c3'))
    browser=Browser(args.port);evidence={'url':args.url}
    def ready():browser.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
    def click(name):
        browser.until('return !document.getElementById('+json.dumps(name)+').disabled;')
        browser.script('document.getElementById('+json.dumps(name)+').click();return true;')
    def workspace():
        browser.script("window.__waypointWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__waypointWorkspace=v);return true;")
        return browser.until('return window.__waypointWorkspace;')
    def runtime(endpoint):
        browser.script("window.__waypointResult=null;(async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__waypointResult=q?JSON.parse(await "+("q.view()" if endpoint=='view' else "q.post('/api/campaign',{})")+")"+(".value" if endpoint!='view' else "")+":await(await fetch('/api/"+endpoint+"')).json();})();return true;")
        return browser.until('return window.__waypointResult;')
    def switch():
        click('open-level-tree')
        browser.script("const node=document.querySelector('.level-node[data-level-id=\"navigation.c3\"]');node.scrollIntoView({block:'nearest'});node.click();return true;")
        origin=browser.script('return performance.timeOrigin;');click('start-selected-level')
        browser.until('return performance.timeOrigin!=='+str(origin)+';',60);ready()
    def shot(name):
        path=args.output.with_name(args.output.stem+'-'+name+'.png')
        path.write_bytes(base64.b64decode(browser.call('WebDriver:TakeScreenshot',{})['value']))
        return str(path.resolve().relative_to(ROOT))
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        browser.navigate(args.url);browser.call('WebDriver:SetWindowRect',{'width':1440,'height':1000});ready()
        before=workspace()['snapshot'];preserved=('control/wheel_controller.py','localization/odometry.py','localization/ekf.py')
        switch();state=workspace()
        assert state['learning']['upgrade_required']
        for path in preserved:assert state['snapshot']['files'][path]==before['files'][path]
        click('open-workspace')
        assert browser.script("return [...document.querySelectorAll('#file-list .task-file')].some(n=>n.title==='navigation/waypoint_controller.py');")
        browser.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(files['navigation/waypoint_controller.py'])+');return true;')
        click('save-workspace');click('test-workspace')
        browser.until("return !document.getElementById('migration-panel').hidden;",90)
        listed=browser.script("return [...document.querySelectorAll('#migration-list summary')].map(n=>n.textContent.split(' · ')[0]);")
        assert not (set(preserved)|{'navigation/waypoint_controller.py'})&set(listed),listed
        click('upgrade-and-test')
        browser.until("return !document.getElementById('deploy-workspace').disabled;",120)
        preparing=runtime('campaign')['attempt'];assert preparing['phase']=='preparing' and preparing['navigation']['reached_count']==0
        click('deploy-workspace')
        browser.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;",120)
        browser.until("const n=JSON.parse(document.getElementById('arena').dataset.waypoints||'null');return n&&n.reached_count>=1;",90)
        current=runtime('view');assert current['payload']['selected_pose']['source_id']=='ekf'
        assert current['payload']['objects']==[]
        assert not any(key.startswith('truth') for key in current['payload'])
        assert 'waypoints' in json.loads(browser.script("return document.getElementById('arena').dataset.visibleLayers;"))
        running=runtime('campaign')['attempt'];evidence['running_navigation']=running['navigation']
        evidence['running']=shot('running')
        click('tab-visualization')
        browser.script("document.querySelector('input[data-layer=waypoints]').click();return true;")
        browser.until("return !JSON.parse(document.getElementById('arena').dataset.visibleLayers).includes('waypoints');")
        browser.script("document.querySelector('input[data-layer=waypoints]').click();return true;")
        browser.until("return JSON.parse(document.getElementById('arena').dataset.visibleLayers).includes('waypoints');")
        click('tab-task')
        browser.until("return document.getElementById('task-status').dataset.status==='passed';",150)
        ended=runtime('campaign');result=ended['attempt']['result'];evidence['result']=result
        assert result['passed'] and result['waypoints_reached']==result['waypoint_count']==4
        assert result['settled_ticks']==30
        assert not {'origin_distance_m','path_length_m'}&result.keys()
        evidence['timing']=ended['attempt']['timing'];evidence['finished']=shot('result')
        after=workspace()['snapshot']
        for path in preserved:assert after['files'][path]==before['files'][path]
        assert after['files']['navigation/waypoint_controller.py']==files['navigation/waypoint_controller.py']
        browser.script("window.__waypointProgress=null;fetch('/api/progress').then(r=>r.json()).then(v=>window.__waypointProgress=v);return true;")
        progress=browser.until('return window.__waypointProgress;')
        assert not progress['developer_mode'] and 'navigation.c3' in progress['completed_levels'];evidence['progress']=progress
        switch();retry=runtime('campaign')
        assert retry['run_id']!=ended['run_id'] and retry['attempt']['phase']=='preparing'
        assert retry['attempt']['navigation']['reached_count']==retry['attempt']['navigation']['settled_ticks']==0
        assert workspace()['snapshot']['revision']==after['revision']
        assert browser.script('return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;')
        evidence.update(player_mode=True,only_waypoint_algorithm_edited=True,old_algorithms_preserved=True,
                        managed_upgrade_only=True,editor_closed_and_locked=True,task_layer_toggle=True,retry_resets_task=True)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: player C2 -> C3, authored waypoint control, safe upgrade/test/deploy, four goals, stop and retry')
    except BaseException as error:
        evidence['error']=str(error)[:2000];evidence['failure']=shot('failure')
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');raise
    finally:browser.close()


if __name__=='__main__':main()
