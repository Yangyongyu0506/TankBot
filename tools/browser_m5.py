#!/usr/bin/env python3
"""Real editor/tree/Test/Deploy QA for revised C3-C5; use a disposable store."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('tests','host','protocol','sdk/python')]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.workspace import WorkspaceStore,starter
from tankbot_host.application import ApplicationState
from weapons_curriculum_support import solutions

# A QA operator, not a player module: reads only the same authorized view and keyboard routes as UI.
MANUAL = '''
window.__manual={history:[],lastPlate:null,error:null};
const operator=window.__manual,params=PARAMETERS;
const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;
const token=(await(await fetch('/api/workspace')).json()).control_token;
const post=async(path,value)=>qa?JSON.parse(await qa.post(path,value)):await(await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':token},body:JSON.stringify(value)})).json();
async function step(){
 if(['passed','ended'].includes(document.getElementById('task-status').dataset.status))return;
 try{
  const view=qa?JSON.parse(await qa.view()):await(await fetch('/api/view')).json();
  const target=view.payload.target_estimates?.[0],own=view.payload.selected_pose?.pose;
  const turret=view.payload.local_observations.find(m=>m.channel==='/robot/turret/joint_states');
  const weapon=view.payload.local_observations.find(m=>m.schema==='weapon_state@1');
  if(target&&own&&turret&&weapon){
   const p=target.payload;let point=[p.x_m,p.y_m];
   if(params.armor){
    const c=Math.cos(p.yaw_rad),s=Math.sin(p.yaw_rad),mounts=[[params.length/2,0],[-params.length/2,0],[0,params.width/2],[0,-params.width/2]];
    let best=-Infinity,index=0;
    for(const [i,m] of mounts.entries()){
     const q=[p.x_m+c*m[0]-s*m[1],p.y_m+s*m[0]+c*m[1]],n=[c*m[0]-s*m[1],s*m[0]+c*m[1]];
     const dx=own.x_m-q[0],dy=own.y_m-q[1],score=(dx*n[0]+dy*n[1])/(Math.hypot(dx,dy)*Math.hypot(...n));
     if(score>best){best=score;index=i;point=q;}
    }
    if(index!==operator.lastPlate){operator.history=[];operator.lastPlate=index;}
   }
   if(operator.history.at(-1)?.tick!==target.simulation_tick)operator.history.push({tick:target.simulation_tick,point});
   operator.history=operator.history.filter(v=>target.simulation_tick-v.tick<=params.hz*params.window).slice(-params.maximum);
   const first=operator.history[0],dt=(target.simulation_tick-first.tick)/params.hz;
   const velocity=dt>0?point.map((v,i)=>(v-first.point[i])/dt):[0,0];
   const age=(view.simulation_tick-target.simulation_tick)/params.hz+Math.hypot(point[0]-own.x_m,point[1]-own.y_m)/params.speed;
   const desired=Math.atan2(point[1]+velocity[1]*age-own.y_m,point[0]+velocity[0]*age-own.x_m);
   const error=Math.atan2(Math.sin(desired-own.yaw_rad-turret.payload.position[0]),Math.cos(desired-own.yaw_rad-turret.payload.position[0]));
   await post('/api/turret_cmd_vel',{velocity_radps:Math.max(-params.rate,Math.min(params.rate,params.gain*error))});
   if(Math.abs(error)<params.tolerance&&weapon.payload.ready)await post('/api/fire',{request_id:crypto.randomUUID()});
  }
 }catch(error){operator.error=String(error);}
 setTimeout(step,params.interval);
}
step();return true;
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8785')
    parser.add_argument('--port',type=int,default=2831)
    parser.add_argument('--prepare-store',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'.m1-cache/weapons-redesign/native-ui.json')
    args=parser.parse_args();args.output=args.output.resolve();config=load_config(ROOT/'config/game.yaml')
    if args.prepare_store:
        if (args.prepare_store/'HEAD.json').exists():raise SystemExit('Use a fresh disposable store')
        WorkspaceStore(args.prepare_store,starter(configure(config,'c3')),config['workspace'])
        state=ApplicationState(config,args.prepare_store.parent/'settings.yaml',args.prepare_store.parent/'progress.json')
        for level in ('c0','c1','c2'):state.complete(state.register_attempt(level),level)
        return
    b=Browser(args.port);evidence={'url':args.url,'capabilities':b.capabilities,'levels':[]}
    def click(identifier):
        b.until("return !document.getElementById("+json.dumps(identifier)+").disabled&&document.getElementById('workspace-panel').dataset.busy!=='true';")
        b.script("document.getElementById("+json.dumps(identifier)+").click();return true;")
    def ready(level=None):
        condition="&&document.getElementById('task-title').textContent.startsWith("+json.dumps(level.upper())+")" if level else ''
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true'"+condition+';',timeout=120)
    def switch(level):
        origin=b.script('return performance.timeOrigin;')
        b.script("document.getElementById('level-select').value="+json.dumps(level)+";return true;");click('start-level')
        b.until('return performance.timeOrigin!=='+str(origin)+';');ready(level)
    def edit(path,source):
        b.script("[...document.querySelectorAll('#file-list button')].find(x=>x.title==="+json.dumps(path)+").click();const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        if not b.script("return document.getElementById('save-workspace').disabled;"):
            click('save-workspace');b.until("return document.getElementById('workspace-panel').dataset.dirty==='false'&&document.getElementById('workspace-panel').dataset.busy==='false';")
    def screenshot(name):
        path=args.output.parent/(args.output.stem+'-'+name+'.png');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']));return path.relative_to(ROOT).as_posix()
    try:
        b.navigate(args.url);b.call('WebDriver:SetWindowRect',{'width':1440,'height':950});ready();switch('c3')
        for index,level in enumerate(('c3','c4','c5')):
            ready(level);click('open-workspace')
            definition=config['campaign']['levels'][level];sources=solutions(configure(config,level))
            paths=definition['tutorial']['lesson']['edit_files']
            for path in paths:edit(path,sources[path])
            actual=b.script("return [...document.querySelectorAll('#file-list button.task-file')].map(n=>n.title);")
            assert set(actual)==set(paths),(level,actual,paths)
            assert b.script("return document.querySelector('.file-tree-guides')?.textContent.includes('──')&&document.querySelector('.file-tree-directory')?.textContent.endsWith('/');")
            tree_shot=screenshot(level+'-tree')
            if not b.script("return document.getElementById('workspace-upgrade').hidden;"):
                click('preview-teaching-upgrade');click('upgrade-and-test')
            else:click('test-workspace')
            report=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s;",timeout=120)
            assert report['last']['status']=='Ready',report
            click('deploy-workspace')
            active=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.status==='Active'&&s;",timeout=120)
            b.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;")
            if level!='c5':
                reference=config['validation']['reference_aim']
                params={'armor':definition['armor_mode'],'length':config['body']['length_m'],'width':config['body']['width_m'],
                    'hz':config['clock']['physics_hz'],'window':reference['velocity_window_s'],'maximum':reference['maximum_track_samples'],
                    'speed':config['weapons']['projectile']['relative_speed_mps'],'rate':reference['manual_aim_rate_radps'],
                    'gain':reference['manual_aim_gain_per_s'],'tolerance':reference['fire_tolerance_rad'],'interval':1000/config['clock']['algorithm_hz']}
                # ExecuteAsyncScript is not needed: initialize an asynchronous task and return immediately.
                b.script('(async()=>{'+MANUAL.replace('PARAMETERS',json.dumps(params)).replace('return true;','')+'})();return true;')
            click('tab-graph');b.until("return document.getElementById('robot-graph-list').textContent.includes('tracking');")
            b.until("return document.getElementById('arena').dataset.targetEstimateX!=='';",timeout=30)
            if level!='c3':b.until("return document.getElementById('arena').dataset.targetEstimateYaw!=='';",timeout=30)
            running_shot=screenshot(level+'-running')
            result=b.until("return document.getElementById('task-status').dataset.status==='passed'&&document.getElementById('task-message').textContent;",timeout=180)
            assert b.script('return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;')
            evidence['levels'].append({'level':level,'report':report['last'],'active':active['active'],'highlighted_files':actual,'result':result,'screenshots':[tree_shot,running_shot]})
            if index<2:switch(('c4','c5')[index])
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print('PASS: C3-C5 real editor tree/highlights, Test/Deploy, manual and autonomous kills',flush=True)
    finally:b.close()


if __name__=='__main__':main()
