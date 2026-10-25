#!/usr/bin/env python3
"""M5 real CodeMirror edit/Test/Deploy and module-graph QA in a disposable store."""
import argparse
import base64
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("tests", "host", "protocol", "sdk/python")]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from weapons_support import solutions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8785")
    parser.add_argument("--port", type=int, default=2831)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/reports/m5-native-browser.json")
    args = parser.parse_args()
    b = Browser(args.port)
    evidence = {"url":args.url,"capabilities":b.capabilities,"levels":[]}
    config = load_config(ROOT / "config/game.yaml")

    def click(identifier):
        b.until("return !document.getElementById("+json.dumps(identifier)+").disabled&&document.getElementById('workspace-panel').dataset.busy!=='true';")
        b.script("document.getElementById("+json.dumps(identifier)+").click();return true;")

    def ready(level=None):
        title_check = "&&document.getElementById('task-title').textContent.startsWith("+json.dumps(level.upper())+")" if level else ""
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true'"+title_check+";",timeout=120)

    def edit(path, source):
        b.script("[...document.querySelectorAll('#file-list button')].find(x=>x.title==="+json.dumps(path)+").click();return true;")
        b.script("const editor=document.querySelector('.cm-content');editor.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        if not b.script("return document.getElementById('save-workspace').disabled;"):
            click("save-workspace")
            b.until("return document.getElementById('workspace-panel').dataset.dirty==='false';")

    try:
        b.navigate(args.url)
        ready()
        page_origin = b.script("return performance.timeOrigin;")
        b.script("document.getElementById('level-select').value='c3';document.getElementById('start-level').click();return true;")
        b.until("return performance.timeOrigin!=="+str(page_origin)+";")
        for level in ("c3", "c4"):
            ready(level)
            assert b.script("return document.getElementById('task-chapter').textContent;") == "Weapons"
            click("open-workspace")
            sources = solutions(configure(config,level))
            paths = ["perception/transforms.py","perception/tracker.py","weapons/auto_aim.py"] if level=="c3" else ["perception/pose_tracker.py","weapons/armor_aim.py"]
            for path in paths:edit(path,sources[path])
            if not b.script("return document.getElementById('workspace-upgrade').hidden;"):
                click("preview-teaching-upgrade");click("upgrade-and-test")
            else:click("test-workspace")
            report = b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s;",timeout=120)
            assert report["last"]["status"]=="Ready",report
            click("deploy-workspace")
            active = b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.status==='Active'&&s;",timeout=120)
            click("close-workspace");click("tab-graph")
            b.until("return document.getElementById('robot-graph-list').textContent.includes('aiming');")
            b.until("return document.querySelector('canvas').dataset.targetEstimateX!=='';",timeout=30)
            pose_yaw = None
            if level == "c4":
                pose_yaw = b.until("const yaw=document.querySelector('canvas').dataset.targetEstimateYaw;return Number.isFinite(Number(yaw))&&yaw!=='';",timeout=30)
            else:
                assert b.script("return document.querySelector('canvas').dataset.targetEstimateYaw==='';")
            screenshot = ROOT / ".m1-cache/m5-qa" / (args.output.stem+"-"+level+".png")
            screenshot.parent.mkdir(exist_ok=True)
            screenshot.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot",{})["value"]))
            result = b.until("return document.getElementById('task-status').dataset.status==='passed'&&document.getElementById('task-message').textContent;",timeout=180)
            assert b.script("return document.documentElement.scrollHeight<=innerHeight+1;")
            evidence["levels"].append({"level":level,"report":report["last"],"active":active["active"],"graph":active["graph"],"result":result,"estimated_yaw_displayed":pose_yaw,"screenshot":screenshot.relative_to(ROOT).as_posix()})
            if level=="c3":
                b.script("document.getElementById('level-select').value='c4';document.getElementById('start-level').click();return true;")
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
        print("PASS: C3/C4 real editor, typed guides, graph Test/Deploy, armor/yaw renderer and fixed viewport",flush=True)
    finally:b.close()


if __name__=="__main__":main()
