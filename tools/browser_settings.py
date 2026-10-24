#!/usr/bin/env python3
"""Exercise settings, real C0 progress and developer displays using disposable profiles."""
import argparse
import base64
from datetime import date
import hashlib
import json
from pathlib import Path
from browser_driver import Browser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8775")
    parser.add_argument("--browser-port", type=int, default=2829)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reports/settings-native.json")
    args = parser.parse_args()
    b = Browser(args.browser_port)
    screenshots = []
    def click(identifier):
        b.script("document.getElementById(" + json.dumps(identifier) + ").click();return true;")
    def press(code, down=True):
        b.script("window.dispatchEvent(new KeyboardEvent(" + json.dumps("keydown" if down else "keyup") + ",{code:" + json.dumps(code) + ",bubbles:true,cancelable:true}));return true;")
    def ready(level):
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true'&&document.getElementById('task-title').textContent.startsWith("+json.dumps(level.upper())+");",timeout=90)
    def request(path, value=None, worker=False):
        b.script("window.__settingsResponse=null;(async()=>{const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;const path="+json.dumps(path)+",value="+json.dumps(value)+";let result;"+
                 ("if(qa){result=path==='/api/view'?{ok:true,value:JSON.parse(await qa.view())}:JSON.parse(await qa.post(path,value??{}));}else " if worker else "")+
                 "{const headers={'Content-Type':'application/json','X-TankBot-Control':(await (await fetch('/api/settings')).json()).control_token};const response=await fetch(path,value===null?undefined:{method:'POST',headers,body:JSON.stringify(value)});result={ok:response.ok,value:await response.json()};}window.__settingsResponse=result;})();return true;")
        return b.until("return window.__settingsResponse;")
    def screenshot(name):
        path=ROOT/".m1-cache"/(args.output.stem+"-"+name+".png")
        path.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot",{})["value"]));screenshots.append(path.relative_to(ROOT).as_posix())
    def choose(level):
        b.script("document.getElementById('level-select').value="+json.dumps(level)+";document.getElementById('start-level').click();return true;");ready(level)
    def mode(enabled):
        click("open-settings")
        b.script("const input=document.getElementById('developer-mode');input.checked="+json.dumps(enabled)+";input.dispatchEvent(new Event('change'));return true;")
        click("save-settings")
        b.until("return document.getElementById('application-mode').textContent==="+json.dumps("开发者模式" if enabled else "玩家模式")+"&&!document.getElementById('settings-dialog').open;",timeout=90)
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
    try:
        b.navigate(args.url);b.call("WebDriver:SetWindowRect",{"width":1440,"height":900});ready("c0")
        assert request("/api/progress")["value"]["completed_levels"]==[],"Use a fresh disposable player save"
        assert b.script("return [...document.getElementById('level-select').options].filter(o=>o.disabled).map(o=>o.value);")==["c1","c2"]
        assert not request("/api/campaign/start",{"level_id":"c2"})["ok"]
        assert not request("/api/developer",worker=True)["ok"]
        click("open-settings");assert b.script("return document.getElementById('settings-dialog').open;")
        for action,code in {"forward":"ArrowUp","editor":"F3","help":"F4","settings":"F9"}.items():
            b.script("document.querySelector('#keyboard-bindings [data-action="+action+"]').click();return true;");press(code)
        screenshot("settings")
        click("save-settings");b.until("return !document.getElementById('settings-dialog').open;")
        assert "↑/S" in b.script("return document.getElementById('task-hints').textContent;")
        saved=request("/api/settings")["value"];assert saved["settings"]["keyboard"]["forward"]=="ArrowUp"
        press("F9");assert b.script("return document.getElementById('settings-dialog').open;")
        press("F9");assert not b.script("return document.getElementById('settings-dialog').open;")
        press("F3");assert b.script("return document.getElementById('workspace-dialog').open;")
        press("F2");assert b.script("return document.getElementById('workspace-dialog').open;")
        press("F3");assert not b.script("return document.getElementById('workspace-dialog').open;")
        press("F4");assert b.script("return document.getElementById('workspace-dialog').open&&!document.getElementById('learning-pane').hidden;")
        press("F3")
        b.script("document.getElementById('arena').focus();return true;")
        origin=request("/api/view",worker=True)["value"]["payload"]["selected_pose"]["pose"]["x_m"]
        press("ArrowUp")
        b.until("return Number(document.getElementById('x').textContent)>"+str(origin+.15)+";",timeout=10)
        press("ArrowUp",False)
        b.navigate(args.url);ready("c0")
        assert request("/api/settings")["value"]["settings"]["keyboard"]["editor"]=="F3"

        # Solve C0 using only its authorized self pose/target and normal actuator routes.
        speed=json.loads((ROOT/"config/m1.json").read_text())["weapons"]["projectile"]["relative_speed_mps"]
        b.script("window.__settingsPlay={started:performance.now(),speed:"+str(speed)+"};return true;")
        b.script('''
          const state=window.__settingsPlay,qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;
          (async()=>{
            const token=(await (await fetch('/api/settings')).json()).control_token;
            const post=async(path,value)=>{
              if(qa){const r=JSON.parse(await qa.post(path,value));if(!r.ok)throw Error(r.value.error);return;}
              const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':token},body:JSON.stringify(value)});
              if(!r.ok)throw Error((await r.json()).error);
            };
            const repeat=async()=>{try{
              if(document.getElementById('task-status').dataset.status==='passed'){state.done=true;return;}
              if(performance.now()-state.started>90000)throw Error('C0 timeout');
              const view=qa?JSON.parse(await qa.view()):await (await fetch('/api/view')).json(),p=view.payload.selected_pose?.pose;
              if(!p){setTimeout(repeat,100);return;}
              const target=view.payload.objects.find(o=>o.kind==='target');
              const moved=Math.hypot(p.x_m,p.y_m)>=1,turned=Math.abs(p.yaw_rad)>=.5;
              await post('/api/cmd_vel',{linear:{x:moved?0:1,y:0,z:0},angular:{x:0,y:0,z:moved&&!turned?1:0}});
              const q=view.payload.local_observations.find(m=>m.channel==='/robot/turret/joint_states').payload.position[0];
              const desired=Math.atan2(target.pose.y_m-p.y_m,target.pose.x_m-p.x_m);
              const e=Math.atan2(Math.sin(desired-p.yaw_rad-q),Math.cos(desired-p.yaw_rad-q));
              await post('/api/turret_cmd_vel',{velocity_radps:Math.max(-2,Math.min(2,4*e))});
              if(Math.abs(e)<.04&&view.payload.local_observations.find(m=>m.schema==='weapon_state@1').payload.ready)await post('/api/fire',{request_id:crypto.randomUUID()});
              setTimeout(repeat,100);
            }catch(error){if(String(error).includes('ATTEMPT_ENDED')){state.done=true;return;}state.error=String(error);}};repeat();
          })();return true;
        ''')
        b.until("if(window.__settingsPlay.error)throw Error(window.__settingsPlay.error);return document.getElementById('task-status').dataset.status==='passed';",timeout=100)
        b.until("return !document.querySelector('#level-select option[value=c1]').disabled;",timeout=15)
        progress=request("/api/progress")["value"];progress.pop("control_token",None);assert progress["completed_levels"]==["c0"]
        print("C0 passed and persisted",flush=True)
        b.navigate(args.url);ready("c0");assert request("/api/progress")["value"]["completed_levels"]==["c0"]
        choose("c1");assert request("/api/view",worker=True)["value"]["payload"]["objects"]==[]
        mode(True);choose("c2")
        click("tab-visualization")
        b.until("return Number(document.getElementById('arena').dataset.truthObjects)>0;",timeout=15)
        listed=b.script("return [...document.querySelectorAll('#layer-list input')].map(i=>i.dataset.layer);")
        for key in ("truth_robot","truth_targets","projectiles","frames","velocities","colliders"):assert key in listed
        for key in ("frames","velocities","colliders"):
            b.script("document.querySelector('#layer-list [data-layer="+key+"]').click();return true;")
        b.until("return document.getElementById('layers-message').textContent.includes('已保存');")
        screenshot("developer")
        b.script("document.querySelector('#layer-list [data-layer=truth_targets]').click();return true;")
        b.until("return !JSON.parse(document.getElementById('arena').dataset.visibleLayers).includes('truth_targets');")
        b.until("return document.getElementById('layers-message').textContent.includes('已保存');")
        assert not request("/api/settings")["value"]["settings"]["layers"]["truth_targets"]
        assert request("/api/developer",worker=True)["ok"]
        assert request("/api/progress")["value"]["completed_levels"]==["c0"]
        mode(False);ready("c1")
        assert not request("/api/developer",worker=True)["ok"]
        assert request("/api/view",worker=True)["value"]["payload"]["objects"]==[]
        assert not request("/api/campaign/start",{"level_id":"c2"})["ok"]
        click("tab-visualization")
        assert not b.script("return !!document.querySelector('#layer-list [data-layer=truth_targets]');")
        screenshot("player")
        dimensions=[]
        for width,height in ((1440,900),(1280,720),(500,740)):
            b.call("WebDriver:SetWindowRect",{"width":width,"height":height});click("open-settings")
            dimensions.append(b.script("const d=document.scrollingElement,r=document.getElementById('settings-dialog').getBoundingClientRect();return {width:innerWidth,height:innerHeight,scroll:d.scrollHeight>d.clientHeight||d.scrollWidth>d.clientWidth,dialogFits:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};"))
            click("close-settings")
        assert all(not row["scroll"] and row["dialogFits"] for row in dimensions),dimensions
        result={"date":date.today().isoformat(),"url":args.url,"browser":b.capabilities["capabilities"]["browserVersion"],
                "remapped_keys_persist":True,"remapped_driving":True,"remapped_editor_help_settings":True,
                "player_locked_api_rejected":True,"real_c0_pass_persisted":progress,"developer_layers":listed,
                "mode_revokes_truth":True,"developer_does_not_unlock_levels":True,"layout":dimensions,"screenshots":screenshots}
        paths=[p for directory in ("host/tankbot_host","web") for p in (ROOT/directory).glob('*') if p.suffix in ('.py','.js','.html','.css')]
        paths.extend(ROOT/p for p in ("config/settings.yaml","requirements.txt","tools/browser_settings.py"))
        result["sources"]={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(args.output)
    finally:b.close()


if __name__ == "__main__":main()
