#!/usr/bin/env python3
"""Real player UI: earn public C0, choose Navigation, then return to Weapons."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--port',type=int,default=2859)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inspect-only',action='store_true',help='Read an already-earned player tree and capture layout without playing or editing')
    args=parser.parse_args()
    from tankbot_host.authority import load_config
    config=load_config(ROOT/'config/game.yaml')
    browser=Browser(args.port);evidence={'url':args.url}
    def ready():browser.until("return document.getElementById('workspace-panel').dataset.ready==='true'&&document.querySelectorAll('.level-node[data-state]').length===document.getElementById('level-select').options.length;",120)
    def click(name):
        browser.until('return !document.getElementById('+json.dumps(name)+').disabled;')
        browser.script('document.getElementById('+json.dumps(name)+').click();return true;')
    def http(path,value=None):
        setup='undefined' if value is None else "{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':window.__treeToken},body:"+json.dumps(json.dumps(value))+"}"
        browser.script("window.__treeHttp=null;fetch("+json.dumps(path)+','+setup+").then(async r=>window.__treeHttp={ok:r.ok,status:r.status,value:await r.json()});return true;")
        return browser.until('return window.__treeHttp;')
    def workspace():return http('/api/workspace')['value']
    def runtime(path):
        browser.script("window.__treeRuntime=null;(async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__treeRuntime=q?JSON.parse(await q.post("+json.dumps(path)+",{})).value:await(await fetch("+json.dumps(path)+")).json();})();return true;")
        return browser.until('return window.__treeRuntime;')
    def nodes():return browser.script("return Object.fromEntries([...document.querySelectorAll('.level-node')].map(n=>[n.dataset.levelId,n.dataset.state]));")
    def node(lid):
        browser.script("const n=[...document.querySelectorAll('.level-node')].find(n=>n.dataset.levelId==="+json.dumps(lid)+");n.scrollIntoView({block:'nearest'});n.click();return true;")
    def open_tree():
        if not browser.script("return document.getElementById('level-tree-dialog').open;"):click('open-level-tree')
    def switch(lid):
        open_tree();node(lid);origin=browser.script('return performance.timeOrigin;');click('start-selected-level')
        browser.until('return performance.timeOrigin!=='+str(origin)+';',60);ready()
        token=workspace()['control_token'];browser.script('window.__treeToken='+json.dumps(token)+';return true;')
    def shot(name):
        path=args.output.with_name(args.output.stem+'-'+name+'.png')
        path.write_bytes(base64.b64decode(browser.call('WebDriver:TakeScreenshot',{})['value']))
        return str(path.resolve().relative_to(ROOT))
    def add_note(path,text):
        existing=workspace()['snapshot']
        if path in existing['files']:
            assert existing['files'][path]==text
            return existing
        click('open-workspace');browser.script("document.getElementById('new-file-path').value="+json.dumps(path)+';return true;');click('new-file')
        browser.until("return document.getElementById('editor-path').textContent.includes("+json.dumps(path)+');')
        browser.script("const editor=document.querySelector('.cm-content');editor.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(text)+');return true;')
        click('save-workspace');browser.until("return document.getElementById('workspace-panel').dataset.dirty==='false';")
        click('close-workspace');return workspace()['snapshot']
    def check_old(snapshot):
        result=http('/api/workspace/revision',{'revision':snapshot['revision']})
        assert result['ok'] and result['value']==snapshot,result
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        browser.navigate(args.url);browser.call('WebDriver:SetWindowRect',{'width':1440,'height':1020});ready()
        initial=workspace();browser.script('window.__treeToken='+json.dumps(initial['control_token'])+';return true;')
        if args.inspect_only:
            progress=http('/api/progress')['value'];assert not progress['developer_mode']
            open_tree();browser.until("return document.querySelectorAll('#level-tree-edges path').length===document.querySelectorAll('.level-node').length-1;")
            evidence['wide']=shot('wide')
            browser.call('WebDriver:SetWindowRect',{'width':500,'height':740});node('navigation.c2')
            layout=browser.script("const d=document.scrollingElement,b=document.getElementById('start-selected-level').getBoundingClientRect(),p=document.getElementById('level-lock-reason').getBoundingClientRect();return {pageFits:d.scrollWidth<=innerWidth&&d.scrollHeight<=innerHeight,buttonVisible:b.top>=0&&b.bottom<=innerHeight,missingVisible:p.top>=0&&p.bottom<=b.top};")
            assert all(layout.values()),layout
            evidence.update(narrow=shot('narrow'),layout=layout,progress=progress)
            args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');print('PASS: current player tree, visible missing prerequisite and narrow action button');return
        p=http('/api/progress')['value'];assert p['completed_levels']==[] and p['unlocked_levels']==['c0'] and not p['developer_mode'],p
        open_tree();browser.until("return document.querySelectorAll('#level-tree-edges path').length===document.querySelectorAll('.level-node').length-1;")
        assert [lid for lid,state in nodes().items() if state=='available']==['c0']
        node('navigation.c0');assert browser.script("return document.getElementById('start-selected-level').disabled;")
        assert 'C0' in browser.script("return document.getElementById('level-lock-reason').textContent;")
        browser.script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'F2',key:'F2',bubbles:true}));return true;")
        assert not browser.script("return document.getElementById('workspace-dialog').open;")
        denied=http('/api/campaign/start',{'level_id':'navigation.c0'});assert denied['status']==400 and 'LEVEL_LOCKED' in denied['value']['error']
        evidence['locked_tree']=shot('locked')
        click('close-level-tree')
        weapons_before=add_note('weapons_notes.py','note: str = "authored in the public introduction"\n')
        # Exercise only ordinary keyboard controls and the C0-authorized snapshot.
        params={'movement':config['campaign']['levels']['c0']['objective']['movement_m'],
                'turn':config['campaign']['levels']['c0']['objective']['turn_rad'],
                'tolerance':config['validation']['reference_aim']['fire_tolerance_rad'],
                'aim_gain':config['validation']['reference_aim']['manual_aim_gain_per_s'],
                'aim_rate':config['validation']['reference_aim']['manual_aim_rate_radps']}
        browser.script("window.__treePlay={done:false,error:null,stage:0,held:new Set(),shots:0};const s=window.__treePlay,p="+json.dumps(params)+";const canvas=document.getElementById('arena');canvas.focus();const key=(code,on)=>{if(s.held.has(code)===on)return;on?s.held.add(code):s.held.delete(code);canvas.dispatchEvent(new KeyboardEvent(on?'keydown':'keyup',{code,key:code,bubbles:true}));};const view=async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;return q?JSON.parse(await q.view()):await(await fetch('/api/view')).json();};const loop=async()=>{try{if(document.getElementById('task-status').dataset.status==='passed'){for(const k of [...s.held])key(k,false);s.done=true;return;}const m=await view(),pose=m.payload.selected_pose?.pose;if(!pose){setTimeout(loop,40);return;}if(s.stage===0){key('KeyW',true);if(Math.hypot(pose.x_m,pose.y_m)>p.movement+.1){key('KeyW',false);s.stage=1;}}else if(s.stage===1){key('KeyA',true);if(Math.abs(pose.yaw_rad)>p.turn+.1){key('KeyA',false);s.stage=2;}}else{const target=m.payload.objects.find(o=>o.kind==='target');if(target){const turret=m.payload.local_observations.find(row=>row.channel==='/robot/turret/joint_states').payload.position[0];const desired=Math.atan2(target.pose.y_m-pose.y_m,target.pose.x_m-pose.x_m)-pose.yaw_rad-turret;const error=Math.atan2(Math.sin(desired),Math.cos(desired));key('KeyJ',false);key('KeyL',false);const velocity_radps=Math.max(-p.aim_rate,Math.min(p.aim_rate,p.aim_gain*error));const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;if(qa)await qa.post('/api/turret_cmd_vel',{velocity_radps});else await fetch('/api/turret_cmd_vel',{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':window.__treeToken},body:JSON.stringify({velocity_radps})});const weapon=m.payload.local_observations.find(row=>row.schema==='weapon_state@1').payload;if(Math.abs(error)<p.tolerance&&weapon.ready){canvas.dispatchEvent(new KeyboardEvent('keydown',{code:'Space',key:' ',bubbles:true}));canvas.dispatchEvent(new KeyboardEvent('keyup',{code:'Space',key:' ',bubbles:true}));s.shots++;}}}setTimeout(loop,30);}catch(error){s.error=String(error);}};loop();return true;")
        browser.until("if(window.__treePlay.error)throw Error(window.__treePlay.error);return window.__treePlay.done;",55)
        browser.until("return document.querySelectorAll('#newly-unlocked-list button').length===2;",20)
        after=http('/api/progress')['value'];assert after['completed_levels']==['c0'] and after['unlocked_levels']==['c0','c1','navigation.c0'],after
        attempt=runtime('/api/campaign')['attempt'];evidence['earned_c0']=attempt['result'];evidence['c0_timing']=attempt['timing'];evidence['unlocked']=after
        open_tree();assert nodes()['c1']==nodes()['navigation.c0']=='available';assert nodes()['c2']==nodes()['navigation.c1']=='locked'
        evidence['two_branches']=shot('unlocked')
        switch('navigation.c0');nav_initial=workspace()['snapshot']
        assert 'weapons_notes.py' not in nav_initial['files'];assert 'control/wheel_controller.py' in nav_initial['files']
        nav_before=add_note('navigation_notes.py','note: str = "independent navigation project"\n')
        click('open-workspace');click('test-workspace')
        status=browser.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s;",120)
        assert status['last']['status']=='Ready',status
        click('close-workspace');evidence['navigation_test']=status['last']
        switch('navigation.c0');assert workspace()['snapshot']==nav_before;check_old(nav_before)
        switch('c1');weapons=workspace()['snapshot']
        assert weapons['files']['weapons_notes.py']==weapons_before['files']['weapons_notes.py'];assert 'navigation_notes.py' not in weapons['files'];check_old(weapons_before)
        clean=runtime('/api/deployment');assert clean['active'] is None and clean['job'] is None and not clean['reports']
        evidence['returned_weapons']=shot('weapons')
        switch('navigation.c0');assert workspace()['snapshot']==nav_before;check_old(nav_before)
        browser.navigate(args.url);ready();assert workspace()['snapshot']==nav_before
        browser.call('WebDriver:SetWindowRect',{'width':500,'height':740});open_tree();node('navigation.c2')
        fit=browser.script("const d=document.scrollingElement,r=document.getElementById('level-tree-dialog').getBoundingClientRect(),s=document.querySelector('.level-tree-scroll');return {pageFits:d.scrollHeight<=innerHeight&&d.scrollWidth<=innerWidth,dialogFits:r.top>=0&&r.left>=0&&r.bottom<=innerHeight&&r.right<=innerWidth,innerScroll:s.scrollHeight>s.clientHeight};")
        assert all(fit.values()),fit;evidence['narrow_layout']=fit;evidence['narrow']=shot('narrow')
        # Space/Enter remain native buttons, and Escape dismisses the native dialog.
        browser.call('WebDriver:PerformActions',{'actions':[{'type':'key','id':'tree-keyboard','actions':[{'type':'keyDown','value':'\ue00c'},{'type':'keyUp','value':'\ue00c'}]}]})
        browser.until("return !document.getElementById('level-tree-dialog').open;")
        final=http('/api/progress')['value'];assert final['completed_levels']==['c0'] and not final['developer_mode'],final
        evidence.update(player_flow=True,no_reference_code=True,independent_projects=True,revision_and_ledger_preserved=True,retry_and_refresh_preserved=True,locked_api_rejected=True,final_progress=final)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: real player C0 -> both branches -> Navigation -> Weapons, preserved projects, tree and narrow layout')
    except BaseException as error:
        evidence['error']=str(error)[:2000];evidence['failure']=shot('failure');args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');raise
    finally:browser.close()


if __name__=='__main__':main()
