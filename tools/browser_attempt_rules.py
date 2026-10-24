#!/usr/bin/env python3
"""Disposable UI acceptance: preparation, deadlines, abort, retry and lethal reflected shots."""
import argparse
import base64
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8785")
    parser.add_argument("--browser-port", type=int, default=2831)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/reports/attempt-rules-native.json")
    args = parser.parse_args()
    if args.prepare:
        import yaml
        sys.path[:0] = [str(ROOT/p) for p in ("host", "protocol", "sdk/python", "tests")]
        from tankbot_host.authority import load_config
        from tankbot_host.campaign import configure
        from tankbot_host.workspace import WorkspaceStore
        from campaign_support import solutions
        if args.prepare.exists(): raise SystemExit("Use a fresh disposable directory")
        args.prepare.mkdir(parents=True)
        config = load_config(ROOT/"config/game.yaml")
        config["host"]["port"]=8785; config["browser"]["runtime_port"]=8786
        for key, seconds in (("c0",2),("c1",8),("c2",30)):
            config["campaign"]["levels"][key]["time_limit_s"]=seconds
        config["scene"]["walls"]=[{"center":[1.5,0],"size":[.05,4]}]
        (args.prepare/"config.yaml").write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
        lesson=configure(config,"c2")
        WorkspaceStore(args.prepare/"workspace",solutions(lesson),lesson["workspace"])
        return
    b=Browser(args.browser_port)
    def click(identifier):
        b.until("return !document.getElementById("+json.dumps(identifier)+").disabled&&document.getElementById('workspace-panel').dataset.busy==='false';")
        b.script("document.getElementById("+json.dumps(identifier)+").click();return true;")
    def request(path, value=None):
        b.script("window.__attemptReply=null;(async()=>{try{const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;const path="+json.dumps(path)+",value="+json.dumps(value or {})+";if(qa){const r=JSON.parse(await qa.post(path,value));if(!r.ok)throw Error(r.value.error);window.__attemptReply=r.value??{accepted:true};}else{const w=await(await fetch('/api/workspace')).json(),r=await fetch(path,path==='/api/campaign'?undefined:{method:'POST',headers:{'Content-Type':'application/json','X-TankBot-Control':w.control_token},body:JSON.stringify(value)});window.__attemptReply=(await r.json())??{accepted:true};if(!r.ok)throw Error(window.__attemptReply.error);}}catch(e){window.__attemptReply={error:String(e)};}})();return true;")
        result=b.until("return window.__attemptReply;")
        assert not result.get("error"),result
        return result
    def status():return request("/api/campaign")["attempt"]
    def ready(level):
        b.until("return !window.__attemptRestarting&&document.getElementById('workspace-panel').dataset.ready==='true'&&document.getElementById('task-title').textContent.startsWith("+json.dumps(level.upper())+");",timeout=90)
    def start(level):
        b.until("const w=document.getElementById('workspace-panel');return w.dataset.busy==='false'&&w.dataset.runtimeBusy==='false'&&w.dataset.dirty==='false';")
        b.script("window.__attemptRestarting=true;document.getElementById('level-select').value="+json.dumps(level)+";return true;")
        click("start-level");ready(level)
    def test():
        click("test-workspace")
        value=b.until("const d=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !d.job&&d.last?.kind==='test'&&d.last;",timeout=90)
        assert value["status"]=="Ready",value
    def deploy():
        click("deploy-workspace")
        b.until("const d=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !d.job&&d.last?.status==='Active';",timeout=90)
    shots=[]
    def screenshot(name):
        path=ROOT/".m1-cache"/(args.output.stem+"-"+name+".png")
        path.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot",{})["value"]));shots.append(path.relative_to(ROOT).as_posix())
    try:
        b.navigate(args.url);b.call("WebDriver:SetWindowRect",{"width":1440,"height":950});ready("c0")
        assert status()["timing"]["started_tick"] is None
        request("/api/turret_cmd_vel",{"velocity_radps":.1})
        b.until("return document.getElementById('task-message').textContent.includes('失败：超时');",timeout=10)
        c0=status();assert c0["result"]["reason"]=="timeout",c0
        start("c1");click("open-workspace")
        before=status();assert before["phase"]=="preparing" and before["timing"]["remaining_s"]==8
        test();assert status()["timing"]["started_tick"] is None
        deploy();first=status();assert first["phase"]=="running",first
        deploy();second=status();assert second["timing"]["started_tick"]==first["timing"]["started_tick"]
        click("editor-finish-level")
        b.until("return document.getElementById('editor-attempt-status').textContent.includes('已主动结束');")
        aborted=status();assert aborted["result"]["reason"]=="aborted"
        click("close-workspace");start("c1");click("open-workspace");test();deploy()
        # Keep the editor open: running attempts keep counting down.
        b.until("return document.getElementById('editor-attempt-status').textContent.includes('失败：超时');",timeout=20)
        timeout=status();assert timeout["timing"]["elapsed_ticks"]==8*60,timeout
        screenshot("timeout-editor");click("close-workspace")
        start("c2");click("open-workspace");test();deploy();click("close-workspace")
        hp=[]
        for value in (3,2,1):
            current=status();assert current["player_hp"]==value,current;hp.append(value)
            request("/api/fire",{"request_id":"return-"+str(value)})
            b.until("return document.getElementById('campaign-summary').textContent.includes("+json.dumps("我方 HP "+str(value-1)+"/3")+");",timeout=10)
        dead=status();hp.append(dead["player_hp"])
        assert dead["result"]["reason"]=="player_dead" and not dead["result"]["passed"],dead
        b.script("window.__deathView=null;(async()=>{const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__deathView=qa?JSON.parse(await qa.view()):await(await fetch('/api/view')).json();})();return true;")
        view=b.until("return window.__deathView;")
        assert view["payload"]["selected_pose"] is None and view["payload"]["local_observations"]==[],view
        screenshot("player-dead")
        layouts=[]
        for width,height in ((1280,800),(500,740)):
            b.call("WebDriver:SetWindowRect",{"width":width,"height":height});click("open-workspace")
            layouts.append(b.script("const d=document.scrollingElement;return {width:innerWidth,height:innerHeight,pageScroll:d.scrollHeight>d.clientHeight||d.scrollWidth>d.clientWidth,editorHeight:document.querySelector('.cm-editor').clientHeight};"));click("close-workspace")
        assert all(not row["pageScroll"] and row["editorHeight"]>20 for row in layouts),layouts
        start("c2");reset=status();assert reset["phase"]=="preparing" and reset["player_hp"]==3
        report={"date":date.today().isoformat(),"url":args.url,"browser":b.capabilities["capabilities"]["browserVersion"],"test_limits_s":[2,8,30],"production_limits_s":[60,60,120],
                "c0_timeout":c0,"test_does_not_start":True,"deployment_starts":first["timing"],"redeploy_keeps_start":True,"abort":aborted,"editor_timeout":timeout,"player_hp":hp,"death":dead,"retry":reset,"layout":layouts,"screenshots":shots}
        paths=[p for directory in ("host/tankbot_host","runtime","sdk/python/tankbot","web","core/src") for p in (ROOT/directory).rglob('*') if p.suffix in ('.py','.js','.html','.css','.rs')]
        paths.extend(ROOT/p for p in ("config/game.yaml","config/player-dependencies.yaml","tools/browser_attempt_rules.py"))
        report["sources"]={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");print(args.output)
    finally:b.close()


if __name__=="__main__":main()
