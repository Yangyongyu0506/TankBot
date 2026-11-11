#!/usr/bin/env python3
"""Isolated C4 -> C5 one-shot planning, edit/test/deploy/complete/retry/back in Firefox."""
import argparse
import base64
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parent))
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True);parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--mode',choices=('native','browser'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--planner',choices=('astar','dijkstra'),default='astar')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--planning-faults',action='store_true')
    args=parser.parse_args()
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from planning_support import standalone_source
    planner_source=standalone_source(args.planner)
    browser=Browser(args.port);evidence={'mode':args.mode,'url':args.url,'planner':args.planner,'seed':args.seed}
    control_cursor={}
    def script(code):return browser.script(code)
    def ready():browser.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
    def click(name):
        browser.until('return !!document.getElementById('+json.dumps(name)+')&&!document.getElementById('+json.dumps(name)+').disabled;',90)
        script('document.getElementById('+json.dumps(name)+').click();return true;')
    def request(path,value=None,runtime=False):
        if path=='/api/campaign':value={**control_cursor,**(value or {})}
        if runtime and args.mode=='browser':
            expression="JSON.parse(await(window.wrappedJSObject?.tankbotQA??window.tankbotQA).post("+json.dumps(path)+','+json.dumps(value or {})+")).value"
        else:
            url=path+('?'+urlencode(value) if path=='/api/campaign' and value else '')
            expression="await(await fetch("+json.dumps(url)+")).json()"
        script("window.__pathReply=null;(async()=>{try{window.__pathReply={value:"+expression+"};}catch(e){window.__pathReply={error:String(e)};}})();return true;")
        reply=browser.until('return window.__pathReply;',120)
        if 'error' in reply:raise AssertionError(reply['error'])
        result=reply['value']
        if isinstance(result,dict) and 'error' in result:raise AssertionError(result['error'])
        if path=='/api/campaign':
            # Match the real UI's independent delta cursor. Repeated full-history
            # serialization would itself block the Core Worker's result delivery.
            if control_cursor.get('run_id')!=result['run_id']:control_cursor.clear()
            points=(result.get('attempt') or {}).get('control_feedback',{}).get('points',[])
            control_cursor.update(run_id=result['run_id'],control_after_tick=points[-1]['simulation_tick'] if points else control_cursor.get('control_after_tick',-1))
        return result
    def view():
        if args.mode=='native':return request('/api/view')
        script("window.__pathView=null;(window.wrappedJSObject?.tankbotQA??window.tankbotQA).view().then(raw=>window.__pathView=JSON.parse(raw));return true;")
        return browser.until('return window.__pathView;')
    def switch(level_id="navigation.c5"):
        click('open-level-tree')
        script("const n=document.querySelector('.level-node[data-level-id=\""+level_id+"\"]');n.scrollIntoView({block:'nearest'});n.click();return true;")
        origin=script('return performance.timeOrigin;');click('start-selected-level')
        browser.until('return performance.timeOrigin!=='+str(origin)+';',60);ready()
    def shot(name):
        path=args.output.with_name(name+'.png');path.write_bytes(base64.b64decode(browser.call('WebDriver:TakeScreenshot',{})['value']))
        return str(path)
    try:
        browser.navigate(args.url);browser.call('WebDriver:SetWindowRect',{'width':1500,'height':1050});ready()
        evidence['environment']={'user_agent':script('return navigator.userAgent;'),
                                 'host_python':sys.version.split()[0],'platform':sys.platform}
        before=request('/api/workspace')['snapshot'];preserved=('control/wheel_controller.py','localization/odometry.py','localization/ekf.py','navigation/path_follower.py')
        switch();workspace=request('/api/workspace');snapshot=workspace['snapshot']
        assert workspace['learning']['upgrade_required']
        for name in preserved:assert snapshot['files'][name]==before['files'][name]
        click('open-workspace')
        assert script("return [...document.querySelectorAll('#file-list .task-file')].some(n=>n.title==='navigation/global_planner.py');")
        script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(planner_source)+');return true;')
        click('save-workspace');click('test-workspace')
        browser.until("return !document.getElementById('migration-panel').hidden;",90)
        entries=script("return [...document.querySelectorAll('#migration-list summary')].map(n=>n.textContent.split(' · ')[0]);")
        assert not set(preserved+('navigation/global_planner.py',))&set(entries)
        click('upgrade-and-test')
        browser.until("return !document.getElementById('deploy-workspace').disabled||document.getElementById('deploy-help').textContent.includes('测试失败');",120)
        assert script("return !document.getElementById('deploy-workspace').disabled;"), 'Snapshot test failed; see captured deployment diagnostics'
        if args.planning_faults:
            failures=[]
            prefix='import numpy as np\nclass GlobalPlanner:\n def __init__(self,*args): pass\n def plan(self,start_xy,goal_xy):\n'
            cases=[('none',prefix+'  return None\n','PLANNING_NO_PATH'),
                   ('dtype',prefix+'  return np.zeros((2,2),dtype=np.float32)\n','PLANNING_PATH_DTYPE'),
                   ('exception','class GlobalPlanner:\n def __init__(self,*args):\n  raise RuntimeError("planning constructor QA evidence")\n','PLANNING_ERROR'),
                   ('infinite_constructor','class GlobalPlanner:\n def __init__(self,*args):\n  while True: pass\n','PLANNING_TIMEOUT')]
            for name,source,code in cases:
                previous=request('/api/deployment',runtime=True)['last']['id']
                script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+');return true;')
                click('save-workspace');click('test-workspace')
                browser.until("const d=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !d.job&&d.last?.id!=="+json.dumps(previous)+"&&d.last?.status==='Failed';",30)
                failed=request('/api/deployment',runtime=True)['last'];assert code in failed['error'],failed
                if name=='exception':assert failed['diagnostic']['path']=='navigation/global_planner.py'
                state=request('/api/campaign',runtime=True)['attempt']
                assert state['status']=='active' and state['timing']['started_tick'] is None
                assert 'route' not in state['global_planning']
                failures.append({'case':name,'result':failed,'tick':state['timing']['elapsed_ticks']})
            evidence['planning_failures']=failures;evidence['failure_feedback_screenshot']=shot('planning-failures')
            previous=request('/api/deployment',runtime=True)['last']['id']
            script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(planner_source)+');return true;')
            click('save-workspace');click('test-workspace')
            browser.until("const d=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !d.job&&d.last?.id!=="+json.dumps(previous)+"&&d.last?.status==='Ready';",90)
        preparing=request('/api/campaign',runtime=True)
        assert preparing['attempt']['phase']=='preparing'
        assert preparing['attempt']['global_planning']['phase']=='waiting'
        assert 'route' not in preparing['attempt']['global_planning']
        identity=preparing['attempt']['global_planning']['task_id']
        test_runtime=request('/api/deployment',runtime=True)
        evidence['snapshot_test']=test_runtime['last']
        assert test_runtime['last']['preparation']['planning_elapsed_ms']<5000
        click('deploy-workspace')
        browser.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;",120)
        browser.until("const p=JSON.parse(document.getElementById('arena').dataset.globalPlanning||'null');return p&&p.route;",90)
        current=view();assert current['payload']['selected_pose']['source_id']=='ekf'
        assert current['payload']['objects']==[] and 'wall_contact' not in json.dumps(current)
        active=request('/api/campaign',runtime=True)['attempt']
        assert 'goal_distance_m' in active['global_planning'] and 'tracking_rmse_m' not in active['global_planning']
        evidence['running']=active['global_planning'];evidence['running_screenshot']=shot('running')
        click('tab-visualization')
        for hidden,shown in [('path','safety_grid'),('safety_grid','path'),('planning_map','path')]:
            script('document.querySelector("input[data-layer='+hidden+']").click();return true;')
            browser.until('const s=JSON.parse(document.getElementById("arena").dataset.visibleLayers);return !s.includes('+json.dumps(hidden)+')&&s.includes('+json.dumps(shown)+');')
            script('document.querySelector("input[data-layer='+hidden+']").click();return true;')
        click('tab-task');deadline=time.monotonic()+150
        ended=None
        while time.monotonic()<deadline:
            state=request('/api/campaign',runtime=True)
            if state['attempt']['status']!='active':ended=state;break
            time.sleep(.5)
        assert ended,'No terminal outcome within acceptance deadline'
        result=ended['attempt']['result'];evidence['result']=result
        runtime=request('/api/deployment',runtime=True);evidence['runtime']=runtime
        if args.mode=='browser':evidence['health']=script("return JSON.parse(document.getElementById('arena').dataset.runtimeHealth||'{}');")
        assert result['passed'],result
        timing=runtime['timing']
        assert timing['budget_ms']==timing['execution_profile']['batch_wall_deadline_ms'] and timing['timeouts']==0
        assert timing['execution_profile']['module_declared_budget_cap_ms']==20
        assert all(row['commit_tick']-row['activation_tick']==6 for row in timing['recent'])
        assert result['task_id']==identity
        assert result['planning_elapsed_ms']<5000
        assert runtime['active']['deployment_id']!=test_runtime['last']['id']
        assert runtime['active']['preparation']['path_id']==result['path_id']
        assert result['settled_ticks']==30
        assert int(script("return document.getElementById('hud-control').dataset.samples;"))>100
        browser.until("return document.getElementById('task-status').dataset.status==='passed';",30)
        assert '追踪RMSE' in script("return document.getElementById('task-message').textContent;")
        evidence['finished_screenshot']=shot('finished')
        after=request('/api/workspace')['snapshot']
        for name in preserved:assert after['files'][name]==before['files'][name]
        assert after['files']['navigation/global_planner.py']==planner_source
        progress=request('/api/progress');assert not progress['developer_mode'] and 'navigation.c5' in progress['completed_levels']
        evidence['progress']=progress
        switch();retry=request('/api/campaign',runtime=True)
        assert retry['run_id']!=ended['run_id']
        assert retry['attempt']['phase']=='preparing' and retry['attempt']['global_planning']['phase']=='waiting'
        assert retry['attempt']['global_planning']['task_id']==identity
        assert 'route' not in retry['attempt']['global_planning']
        assert request('/api/workspace')['snapshot']['revision']==after['revision']
        switch('navigation.c4')
        returned=request('/api/workspace')['snapshot']
        for name in preserved+('my_notes.py',):assert returned['files'][name]==after['files'][name]
        assert returned['files']['navigation/global_planner.py']==planner_source
        evidence['returned_c4']=True
        assert script('return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;')
        evidence.update(passed=True,player_mode=True,old_sources_preserved=True,managed_upgrade_only=True,
                        editor_closed_and_locked=True,independent_path_layers=True,retry_same_reference=True)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: '+args.mode+' real C4 -> C5 edit, preview upgrade, full plan test, replan deploy, complete, retry and return C4')
    except BaseException as error:
        try:evidence['failure_runtime']=request('/api/deployment',runtime=True)
        except Exception as diagnostic_error:evidence['diagnostic_error']=str(diagnostic_error)
        evidence['error']=str(error)[:6000];evidence['failure_screenshot']=shot('failure')
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');raise
    finally:browser.close()


if __name__=='__main__':main()
