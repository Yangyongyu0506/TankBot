#!/usr/bin/env python3
"""Check developer enemy models and continuous spin using disposable local saves."""
import argparse
import base64
import json
import math
from pathlib import Path
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8795')
    parser.add_argument('--port',type=int,default=2832)
    parser.add_argument('--initial-level',default='c5')
    parser.add_argument('--preserved-file',help='Optional existing player file to compare across switches')
    parser.add_argument('--output',type=Path,default=ROOT/'.m1-cache/c5-developer-render/native-ui.json')
    args=parser.parse_args();args.output=args.output.resolve();b=Browser(args.port)
    evidence={'url':args.url,'levels':[]}
    def ready(level):
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true'&&document.getElementById('task-title').textContent.startsWith("+json.dumps(level.upper())+");",timeout=120)
    def choose(level):
        origin=b.script('return performance.timeOrigin;')
        b.script("document.getElementById('level-select').value="+json.dumps(level)+";document.getElementById('start-level').click();return true;")
        b.until('return performance.timeOrigin!=='+str(origin)+';');ready(level)
    def show(enabled):
        b.script("const input=document.querySelector('[data-layer=truth_targets]');if(!input||input.disabled)throw Error('Developer truth toggle unavailable');if(input.checked!=="+json.dumps(enabled)+")input.click();return true;")
        b.until("return Boolean(document.getElementById('arena').dataset.targetModel)==="+json.dumps(enabled)+";")
    def sample(duration_ms):
        b.script('''
          window.__chassisProbe={samples:[],started:performance.now(),done:false};
          const state=window.__chassisProbe;
          function sample(now){
            const data=document.getElementById('arena').dataset;
            if(data.targetYaw!=='')state.samples.push({time:now,x:Number(data.targetX),y:Number(data.targetY),yaw:Number(data.targetYaw),model:data.targetModel});
            if(now-state.started<'''+str(duration_ms)+''')requestAnimationFrame(sample);else state.done=true;
          }
          requestAnimationFrame(sample);return true;
        ''')
        return b.until('return window.__chassisProbe.done&&window.__chassisProbe.samples;',timeout=20)
    def shot(name):
        path=args.output.parent/(args.output.stem+'-'+name+'.png');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(base64.b64decode(b.call('WebDriver:TakeScreenshot',{})['value']))
        return path.relative_to(ROOT).as_posix()
    try:
        b.navigate(args.url);b.call('WebDriver:SetWindowRect',{'width':1440,'height':950});ready(args.initial_level)
        assert b.script("return document.getElementById('arena').dataset.developerMode==='true';"),'Use --developer and disposable settings/save/store paths'
        def workspace():
            b.script("window.__chassisWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__chassisWorkspace=v);return true;")
            return b.until('return window.__chassisWorkspace;')
        before=workspace()['snapshot']['files'].get(args.preserved_file) if args.preserved_file else None
        if args.preserved_file:assert before is not None,'preserved-file must already exist'
        for level in ('c5','c2'):
            choose(level);show(True)
            assert b.script("return [...document.querySelectorAll('#layer-list input')].every(input=>!input.disabled);")
            own=b.script("return document.getElementById('arena').dataset.model;")
            samples=sample(5000 if level=='c5' else 1000)
            assert len(samples)>20,samples
            turn=sum(math.atan2(math.sin(c['yaw']-a['yaw']),math.cos(c['yaw']-a['yaw'])) for a,c in zip(samples,samples[1:]))
            distance=math.hypot(samples[-1]['x']-samples[0]['x'],samples[-1]['y']-samples[0]['y'])
            expected='radial-omni-x-v1' if level=='c5' else 'tracked-differential-v1'
            assert {s['model'] for s in samples}=={expected}
            assert own=='tracked-differential-v1','Start this probe with --chassis differential'
            if level=='c5':
                calibration=workspace()['learning']['lesson']['calibration']
                assert calibration['body_length_m']==.42 and calibration['body_width_m']==.42
                assert calibration['armor_mounts'][0]==[.21,0.,0.]
                assert calibration['armor_measurement_covariance']==[[.03**2,0],[0,.005**2]]
                assert 'gps_mount' not in calibration
                assert turn>math.tau,(turn,samples[-1])
                assert distance>.5,distance
                assert len({round(s['yaw'],4) for s in samples})>50,'RAF must interpolate heading'
            else:assert abs(turn)<.1 and distance>.1,(turn,distance)
            screenshot=shot(level)
            show(False);show(True)
            evidence['levels'].append({'level':level,'own_model':own,'enemy_model':expected,'samples':len(samples),'turn_rad':turn,'displacement_m':distance,'layers_toggleable':True,'screenshot':screenshot})
            if args.preserved_file:assert workspace()['snapshot']['files'][args.preserved_file]==before
        if args.preserved_file:evidence['existing_source_preserved']=True
        # Closing the developer grant rebuilds the UI/Authority; player data stays restricted.
        b.script("document.getElementById('open-settings').click();const input=document.getElementById('developer-mode');input.checked=false;input.dispatchEvent(new Event('change'));document.getElementById('save-settings').click();return true;")
        b.until("return document.getElementById('arena').dataset.developerMode==='false'&&document.getElementById('workspace-panel').dataset.ready==='true';",timeout=120)
        assert b.script("return !document.querySelector('[data-layer=velocities]');")
        b.script('''
          window.__developerResponse=null;
          (async()=>{
            const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;
            if(qa)window.__developerResponse=JSON.parse(await qa.post('/api/developer',{}));
            else {const r=await fetch('/api/developer');window.__developerResponse={ok:r.ok,value:await r.json()};}
          })();return true;
        ''')
        response=b.until('return window.__developerResponse;')
        assert not response['ok'] and response['value']['error']=='UNAUTHORIZED',response
        evidence['player_grant_revoked']=True
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(evidence,ensure_ascii=False,indent=2))
    finally:b.close()


if __name__=='__main__':main()
