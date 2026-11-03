#!/usr/bin/env python3
"""Disposable Firefox C0 plots -> preserved controller -> C1 odometry deployment."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ("host","protocol","sdk/python","tests")]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",required=True)
    parser.add_argument("--port",type=int,default=2839)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from navigation_support import solution
    c1_config=configure(load_config(ROOT/"config/game.yaml"),"navigation.c1")
    files=solution(c1_config)
    browser=Browser(args.port)
    evidence={"url":args.url}
    def ready():browser.until("return document.getElementById('workspace-panel').dataset.ready==='true';",120)
    def click(name):
        browser.until("return !document.getElementById("+json.dumps(name)+").disabled;")
        browser.script("document.getElementById("+json.dumps(name)+").click();return true;")
    def workspace():
        browser.script("window.__odomWorkspace=null;fetch('/api/workspace').then(r=>r.json()).then(v=>window.__odomWorkspace=v);return true;")
        return browser.until("return window.__odomWorkspace;")
    def status():
        browser.script("window.__odomAttempt=null;(async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__odomAttempt=q?JSON.parse(await q.post('/api/campaign',{})).value:await(await fetch('/api/campaign')).json();})();return true;")
        return browser.until("return window.__odomAttempt;")
    def view():
        browser.script("window.__odomView=null;(async()=>{const q=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__odomView=q?JSON.parse(await q.view()):await(await fetch('/api/view')).json();})();return true;")
        return browser.until("return window.__odomView;")
    def switch(level):
        origin=browser.script("return performance.timeOrigin;")
        browser.script("document.getElementById('level-select').value="+json.dumps(level)+";return true;")
        click("start-level");browser.until("return performance.timeOrigin!=="+str(origin)+";");ready()
    def edit(source):
        browser.script("const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        if not browser.script("return document.getElementById('save-workspace').disabled;"):click("save-workspace")
    def shot(name):
        path=args.output.with_name(args.output.stem+"-"+name+".png")
        path.write_bytes(base64.b64decode(browser.call("WebDriver:TakeScreenshot",{})["value"]))
        return str(path.resolve().relative_to(ROOT))
    def deploy_and_wait():
        browser.until("return !document.getElementById('deploy-workspace').disabled;",90)
        assert status()["attempt"]["phase"]=="preparing"
        click("deploy-workspace")
        browser.until("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled;",90)
        click("tab-control")
        browser.until("return Number(document.getElementById('hud-control').dataset.samples)>10;",30)
        assert browser.script("return document.querySelectorAll('#hud-control .control-plot').length===4;")
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        browser.navigate(args.url);browser.call("WebDriver:SetWindowRect",{"width":1440,"height":950});ready()
        switch("navigation.c0")
        click("open-workspace");edit(files["control/wheel_controller.py"])
        click("test-workspace")
        browser.until("return !document.getElementById('migration-panel').hidden||!document.getElementById('deploy-workspace').disabled;",90)
        if browser.script("return !document.getElementById('migration-panel').hidden;"):
            click("upgrade-and-test")
        deploy_and_wait()
        click("expand-control")
        assert browser.script("return document.getElementById('control-dialog').open;")
        evidence["c0_running"]=shot("c0-curves")
        click("close-control")
        browser.until("return document.getElementById('task-status').dataset.status==='passed';",90)
        c0=status();evidence["c0_result"]=c0["attempt"]["result"]
        controller=workspace()["snapshot"]["files"]["control/wheel_controller.py"]
        switch("navigation.c1")
        unlocked=workspace()
        assert unlocked["snapshot"]["files"]["control/wheel_controller.py"]==controller
        assert unlocked["learning"]["upgrade_required"]
        click("open-workspace")
        assert browser.script("return [...document.querySelectorAll('#file-list .task-file')].some(n=>n.title==='localization/odometry.py');")
        edit(files["localization/odometry.py"])
        click("test-workspace")
        browser.until("return !document.getElementById('migration-panel').hidden;")
        listed=browser.script("return [...document.querySelectorAll('#migration-list summary')].map(n=>n.textContent.split(' · ')[0]);")
        assert "control/wheel_controller.py" not in listed and "localization/odometry.py" not in listed,listed
        click("upgrade-and-test");deploy_and_wait()
        assert workspace()["snapshot"]["files"]["control/wheel_controller.py"]==controller
        click("expand-control")
        evidence["c1_running"]=shot("c1-curves")
        click("close-control")
        browser.until("return document.getElementById('task-status').dataset.status==='passed';",90)
        c1=status();evidence["c1_result"]=c1["attempt"]["result"]
        assert view()["payload"]["selected_pose"]["source_id"]=="odometry"
        assert set(c1["attempt"]["live_metrics"])=={"rmse_m","yaw_rmse_rad","scored_samples"}
        points=c1["attempt"]["control_feedback"]["points"]
        assert len(points)>100 and len(points)<=c1_config["campaign"]["levels"]["navigation.c1"]["visualization"]["control_feedback"]["history_points"]
        evidence["control_samples"]=len(points)
        click("expand-control")
        assert browser.script("return [...document.querySelectorAll('#control-dialog .control-plot')].every(n=>{const r=n.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;});")
        evidence["c1_result_screenshot"]=shot("c1-result")
        click("close-control")
        before=workspace();switch("navigation.c1")
        assert workspace()["snapshot"]["files"]==before["snapshot"]["files"]
        after=status()
        assert after["run_id"]!=c1["run_id"] and not after["attempt"]["control_feedback"]["points"]
        assert after["attempt"]["live_metrics"]["rmse_m"] is None
        switch("navigation.c0")
        assert workspace()["snapshot"]["files"]["control/wheel_controller.py"]==controller
        assert browser.script("return document.scrollingElement.scrollHeight<=innerHeight&&document.scrollingElement.scrollWidth<=innerWidth;")
        evidence.update(controller_preserved=True,managed_upgrade_only=True,estimated_pose_only=True,retry_clears_feedback=True)
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
        print("PASS: C0/C1 control plots, preserved controller, typed odometry edit/test/deploy, estimated view, both RMSEs and retry")
    except BaseException:
        evidence["failure_screenshot"]=shot("failure")
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
        raise
    finally:browser.close()


if __name__=="__main__":main()
