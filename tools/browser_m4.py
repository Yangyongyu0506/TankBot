#!/usr/bin/env python3
"""Play C0–C2 through the real UI; use a disposable store and --browser-qa for WASM."""
import argparse
import base64
from datetime import date
import hashlib
import json
import yaml
from pathlib import Path
import sys
from browser_driver import Browser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from campaign_support import TRANSFORMS, EMA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765/?runtime=browser")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reports/m4-browser.json")
    parser.add_argument("--learning", action="store_true", help="Check lesson guides, type help and SE(3) matrix experiment")
    args = parser.parse_args()
    b = Browser()
    learning_evidence = {"lessons": [], "screenshots": []}

    def screenshot(suffix):
        path = ROOT / ".m1-cache" / (args.output.stem + "-" + suffix + ".png")
        path.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot", {})["value"]))
        learning_evidence["screenshots"].append(path.relative_to(ROOT).as_posix())

    def ready(level):
        return b.until("return document.getElementById('workspace-panel').dataset.ready==='true'&&document.getElementById('task-title').textContent.startsWith("+json.dumps(level.upper())+");", timeout=90)

    def click(identifier):
        b.until("return !document.getElementById("+json.dumps(identifier)+").disabled&&document.getElementById('workspace-panel').dataset.busy==='false';")
        b.script("document.getElementById("+json.dumps(identifier)+").click();return true;")

    def edit(path, source):
        b.script("[...document.querySelectorAll('#file-list button')].find(button=>button.title==="+json.dumps(path)+").click();return true;")
        b.script("const editor=document.querySelector('.cm-content');editor.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        b.until("return !document.getElementById('save-workspace').disabled;")

    def deploy():
        click("test-workspace")
        status = b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s;", timeout=90)
        assert status["last"]["status"] == "Ready", status
        click("deploy-workspace")
        status = b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.status==='Active'&&s;", timeout=90)
        click("close-workspace")
        return status["active"]

    def next_level(level):
        b.script("document.getElementById('level-select').value="+json.dumps(level)+";document.getElementById('start-level').click();return true;")
        ready(level)

    def check_learning(level):
        click("open-workspace")
        if b.script("return document.getElementById('learning-pane').hidden;"):
            click("toggle-learning")
        assert b.script("return document.getElementById('learning-lesson').textContent.includes("+json.dumps(level.upper())+");")
        learning_evidence["lessons"].append(level)
        if level == "c0":
            b.script("window.dispatchEvent(new KeyboardEvent('keydown',{key:'F1',code:'F1',bubbles:true}));return true;")
            assert b.script("return document.getElementById('learning-pane').hidden&&document.getElementById('workspace-dialog').open;")
            b.script("window.dispatchEvent(new KeyboardEvent('keydown',{key:'F1',code:'F1',bubbles:true}));return true;")
            assert not b.script("return document.getElementById('learning-pane').hidden;")
        if level == "c1":
            assert "NDArray[np.float64]" in b.script("return document.getElementById('editor-contract').textContent;")
            color = b.script("const span=[...document.querySelectorAll('.cm-line span')].find(node=>node.textContent.includes('返回 T_map_radar'));return span&&getComputedStyle(span).color;")
            assert color == "rgb(184, 217, 155)", color
            learning_evidence["docstring_color"] = color
            b.script("document.querySelector('[data-tab=types]').click();document.getElementById('type-search').value='Pose2D';document.getElementById('type-search').dispatchEvent(new Event('input'));document.querySelector('#type-list button').click();return true;")
            text = b.script("return document.getElementById('type-detail').textContent;")
            assert "x_m: float" in text and "yaw_rad: float" in text
            screenshot("types")
            b.script("document.querySelector('[data-tab=matrix]').click();return true;")
            point = json.loads(b.script("return document.getElementById('matrix-canvas').dataset.result;"))
            assert all(abs(a-c)<1e-8 for a,c in zip(point,[1,5,0,1])), point
            screenshot("matrix")
            b.script("const p=document.getElementById('learning-matrix');p.scrollTop=p.scrollHeight;return true;")
            screenshot("matrix-product")
            b.script("document.getElementById('matrix-kind').value='0';document.getElementById('matrix-kind').dispatchEvent(new Event('change'));return true;")
            direction = json.loads(b.script("return document.getElementById('matrix-canvas').dataset.result;"))
            assert all(abs(a-c)<1e-8 for a,c in zip(direction,[0,2,0,0])), direction
            assert "×" in b.script("return document.getElementById('matrix-calculation').textContent;")
            b.call("WebDriver:SetWindowRect", {"width": 500, "height": 740})
            narrow = b.script("const d=document.scrollingElement,p=document.getElementById('learning-pane').getBoundingClientRect();return {scroll:d.scrollWidth>d.clientWidth||d.scrollHeight>d.clientHeight,visible:p.width>0&&p.height>0&&p.right<=innerWidth};")
            assert narrow == {"scroll": False, "visible": True}, narrow
            learning_evidence["narrow_help"] = narrow
            click("close-learning")
            b.call("WebDriver:SetWindowRect", {"width": 1440, "height": 900})
            edit("perception/transforms.py", "from tankbot import Pose2D\nown_pose: Pose2D\nown_pose.")
            b.script("const e=document.querySelector('.cm-content');e.dispatchEvent(new KeyboardEvent('keydown',{key:' ',code:'Space',ctrlKey:true,bubbles:true}));return true;")
            completion = b.until("const box=document.querySelector('.cm-tooltip-autocomplete');return box?.textContent;")
            assert "x_m" in completion and "yaw_rad" in completion, completion
            learning_evidence.update({"point": point, "direction": direction, "completion": completion})
            b.script("document.querySelector('.cm-content').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));return true;")
            edit("perception/transforms.py", TRANSFORMS)
        if not b.script("return document.getElementById('learning-pane').hidden;"):
            click("close-learning")
        click("close-workspace")

    def play(level):
        # This driver only uses the published view, ordinary control routes, and known gun calibration.
        speed = yaml.safe_load((ROOT / "config/game.yaml").read_text())["weapons"]["projectile"]["relative_speed_mps"]
        b.script("window.__m4Playing={level:"+json.dumps(level)+",speed:"+json.dumps(speed)+"};return true;")
        b.script('''
          const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;
          const state=window.__m4Playing;state.samples=[];state.moved=false;state.turned=false;state.started=performance.now();
          (async()=>{
            const workspace=await (await fetch('/api/workspace')).json();
            const post=async(path,value)=>{
              if(qa){const r=JSON.parse(await qa.post(path,value));if(!r.ok)throw Error(r.value.error||'Control rejected');return r.value;}
              const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':workspace.control_token},body:JSON.stringify(value)});
              const result=await r.json();if(!r.ok)throw Error(result.error||'Control rejected');return result;
            };
            const view=()=>qa?qa.view().then(JSON.parse):fetch('/api/view').then(r=>r.json());
            const repeat=async()=>{
              try{
                if(document.getElementById('task-status').dataset.status==='passed'){state.done=true;return;}
                if(performance.now()-state.started>110000)throw Error('play timeout');
                const m=await view(),p=m.payload.selected_pose?.pose;
                if(!p){setTimeout(repeat,100);return;}
                let x,y,vx=0,vy=0,sampleTick=m.simulation_tick;
                if(state.level==='c0'){
                  const target=m.payload.objects.find(o=>o.kind==='target');
                  x=target.pose.x_m;y=target.pose.y_m;
                  state.moved ||= Math.hypot(p.x_m,p.y_m)>=1;
                  state.turned ||= Math.abs(p.yaw_rad)>=.5;
                  await post('/api/cmd_vel',{linear:{x:state.moved?0:1,y:0,z:0},angular:{x:0,y:0,z:state.moved&&!state.turned?1:0}});
                }else{
                  if(m.payload.objects.length)throw Error('hidden truth object leaked');
                  const e=m.payload.target_estimates?.[0];
                  if(!e){setTimeout(repeat,100);return;}
                  x=e.payload.x_m;y=e.payload.y_m;sampleTick=e.simulation_tick;
                  if(!state.samples.length||state.samples.at(-1).tick!==sampleTick)state.samples.push({x,y,tick:sampleTick});
                  state.samples=state.samples.filter(row=>sampleTick-row.tick<=60);
                  if(state.samples.length>1){const first=state.samples[0],dt=(sampleTick-first.tick)/60;vx=(x-first.x)/dt;vy=(y-first.y)/dt;}
                }
                const lead=Math.hypot(x-p.x_m,y-p.y_m)/state.speed+(m.simulation_tick-sampleTick)/60;
                const desired=Math.atan2(y+vy*lead-p.y_m,x+vx*lead-p.x_m);
                const q=m.payload.local_observations.find(row=>row.channel==='/robot/turret/joint_states').payload.position[0];
                const error=Math.atan2(Math.sin(desired-p.yaw_rad-q),Math.cos(desired-p.yaw_rad-q));
                await post('/api/turret_cmd_vel',{velocity_radps:Math.max(-2,Math.min(2,4*error))});
                const weapon=m.payload.local_observations.find(row=>row.schema==='weapon_state@1').payload;
                if(Math.abs(error)<.06&&weapon.ready)await post('/api/fire',{request_id:crypto.randomUUID()});
                state.lastTick=m.simulation_tick;
                setTimeout(repeat,100);
              }catch(error){
                if(String(error).includes('ATTEMPT_ENDED')){state.done=true;return;}
                state.error=String(error);
              }
            };repeat();
          })();return true;
        ''')
        b.until("if(window.__m4Playing.error)throw Error(window.__m4Playing.error);return document.getElementById('task-status').dataset.status==='passed';", timeout=120)
        b.script("window.__m4Result=null;(async()=>{const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__m4Result=qa?JSON.parse(await qa.post('/api/campaign',{})).value:await (await fetch('/api/campaign')).json();})();return true;")
        return b.until("return window.__m4Result;")

    try:
        b.navigate(args.url)
        if args.learning:
            b.call("WebDriver:SetWindowRect", {"width": 1440, "height": 900})
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';", timeout=90)
        if not b.script("return document.getElementById('task-title').textContent.startsWith('C0');"):
            next_level("c0")
        ready("c0")
        if args.learning: check_learning("c0")
        c0 = play("c0")
        print("C0 passed", flush=True)
        next_level("c1")
        if args.learning: check_learning("c1")
        click("open-workspace")
        if not b.script("return document.getElementById('learning-pane').hidden;"): click("close-learning")
        edit("perception/transforms.py", TRANSFORMS)
        c1_deployment = deploy()
        b.until("return document.getElementById('arena').dataset.targetEstimateX!=='';")
        c1 = play("c1")
        print("C1 passed", flush=True)
        next_level("c2")
        if args.learning: check_learning("c2")
        b.script("window.__m4Sources=null;fetch('/api/workspace').then(r=>r.json()).then(w=>window.__m4Sources=w.snapshot.files);return true;")
        files = b.until("return window.__m4Sources;")
        assert files["perception/transforms.py"] == TRANSFORMS
        assert "perception/tracker.py" in files
        click("open-workspace")
        if not b.script("return document.getElementById('learning-pane').hidden;"): click("close-learning")
        edit("perception/tracker.py", EMA)
        c2_deployment = deploy()
        b.until("return document.getElementById('arena').dataset.targetEstimateX!=='';")
        image_path = ROOT / ".m1-cache" / (args.output.stem + "-tracking.png")
        image_path.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot", {})["value"]))
        c2 = play("c2")
        print("C2 passed", flush=True)
        assert len({c0["run_id"], c1["run_id"], c2["run_id"]}) == 3
        assert c2["attempt"]["enemy_hp"] == 0
        dimensions = []
        for width, height in ((1280, 800), (500, 740)):
            b.call("WebDriver:SetWindowRect", {"width": width, "height": height})
            value = b.script("const d=document.scrollingElement;return {width:innerWidth,height:innerHeight,scrollHeight:d.scrollHeight,clientHeight:d.clientHeight,scrollWidth:d.scrollWidth,clientWidth:d.clientWidth};")
            assert value["scrollHeight"] == value["clientHeight"] and value["scrollWidth"] == value["clientWidth"], value
            dimensions.append(value)
        capabilities = b.capabilities["capabilities"]
        report = {"date": date.today().isoformat(), "url": args.url,
                  "browser": {key: capabilities[key] for key in ("browserName", "browserVersion", "platformName")},
                  "c0": c0, "c1": c1, "c2": c2, "c1_deployment": c1_deployment, "c2_deployment": c2_deployment,
                  "source_preserved": True, "new_run_per_level": True, "layout": dimensions,
                  "learning_checks": args.learning,
                  "learning_evidence": learning_evidence,
                  "screenshot": str(image_path.relative_to(ROOT))}
        report["artifacts"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in
                               ("config/game.yaml", "package-lock.json", "target/debug/core_worker", "build/web/editor-bundle.js", "build/browser/authority-bundle.json", "build/browser/player-bundle.json", "target/wasm32-unknown-unknown/release/tankbot_core.wasm")}
        source_paths = [path for directory in ("host", "protocol", "runtime", "sdk/python", "web", "core/src", "docs/schemas")
                        for path in (ROOT / directory).rglob("*") if path.suffix in (".py", ".js", ".html", ".css", ".rs", ".json")]
        source_paths += [ROOT / "tools/browser_m4.py", ROOT / "tests/campaign_support.py"]
        report["sources"] = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source_paths)}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
        print(args.output)
    finally:
        b.close()


if __name__ == "__main__":
    main()
