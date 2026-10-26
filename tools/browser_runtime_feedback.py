#!/usr/bin/env python3
"""Real editor QA for dependency rejection, NumPy matrices, print and tracebacks."""
import argparse
import base64
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
from campaign_support import TRANSFORMS

MATRIX_TEST='''import unittest
import numpy as np
from tankbot import TargetEstimate
from tankbot.transforms import target_positions
class MatrixTest(unittest.TestCase):
    def test_numpy_matrix(self) -> None:
        value: TargetEstimate = TargetEstimate(1.0, 2.0, np.eye(2, dtype=np.float64))
        self.assertEqual(value.covariance.shape, (2, 2))
        self.assertFalse(value.covariance.flags.writeable)
        self.assertEqual(target_positions(()).shape, (0, 2))
        print("matrix feedback", value.covariance.shape)
'''


def algorithm(fault=False):
    code=TRANSFORMS.replace("def radar_to_map", "calls: int = 0\n\ndef radar_to_map")
    return code.replace("    c: float =", "    global calls\n    calls += 1\n    print('player feedback', calls)\n"+
                        ("    if calls > 8:\n        raise ValueError('runtime log demo')\n" if fault else "")+"    c: float =")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-store",type=Path)
    parser.add_argument("--url",default="http://127.0.0.1:8785")
    parser.add_argument("--browser-port",type=int,default=2831)
    parser.add_argument("--output",type=Path,default=ROOT/"docs/reports/runtime-feedback-native.json")
    args=parser.parse_args()
    if args.prepare_store:
        sys.path[:0]=[str(ROOT/name) for name in ("host","protocol","sdk/python")]
        from tankbot_host.authority import load_config
        from tankbot_host.campaign import configure
        from tankbot_host.workspace import WorkspaceStore,starter
        config=configure(load_config(ROOT/"config/game.yaml"),"c1")
        if (args.prepare_store/"HEAD.json").exists():raise SystemExit("Use a fresh disposable store")
        files=starter(config);files["perception/transforms.py"]=algorithm()
        files["campaign_robot.py"]=files["campaign_robot.py"].replace('            ctx.publish("target", estimate,',
            '            estimate = TargetEstimate(estimate.x_m, estimate.y_m, np.eye(2, dtype=np.float64))\n            ctx.publish("target", estimate,')
        files["tests/test_numpy.py"]=MATRIX_TEST
        WorkspaceStore(args.prepare_store,files,config["workspace"]);return
    b=Browser(args.browser_port)
    def click(identifier):
        b.until("return !document.getElementById("+json.dumps(identifier)+").disabled&&document.getElementById('workspace-panel').dataset.busy==='false';")
        b.script("document.getElementById("+json.dumps(identifier)+").click();return true;")
    def edit(source,path="perception/transforms.py"):
        b.script("[...document.querySelectorAll('#file-list button')].find(n=>n.title==="+json.dumps(path)+").click();const e=document.querySelector('.cm-content');e.focus();document.execCommand('selectAll');document.execCommand('insertText',false,"+json.dumps(source)+");return true;")
        b.until("return !document.getElementById('save-workspace').disabled;")
        click("save-workspace")
        b.until("return document.getElementById('workspace-panel').dataset.dirty==='false'&&document.getElementById('workspace-panel').dataset.busy==='false';")
    def test():
        previous=b.script("return JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}').last?.id??null;")
        click("test-workspace")
        result=b.until("const root=document.getElementById('workspace-panel'),s=JSON.parse(root.dataset.deployment||'{}');return !s.job&&s.last?.kind==='test'&&s.last.revision===root.dataset.revision&&s.last.id!=="+json.dumps(previous)+"&&s.last;",timeout=90)
        return result
    def deploy():
        click("deploy-workspace")
        active=b.until("const s=JSON.parse(document.getElementById('workspace-panel').dataset.deployment||'{}');return !s.job&&s.last?.status==='Active'&&s.active;",timeout=90)
        b.until("return !document.getElementById('workspace-dialog').open;")
        b.script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'F2',key:'F2',bubbles:true}));return true;")
        assert b.script("return !document.getElementById('workspace-dialog').open&&document.getElementById('open-workspace').disabled&&document.activeElement.id==='arena';")
        return active
    def screenshot(suffix):
        path=ROOT/".m1-cache"/(args.output.stem+"-"+suffix+".png")
        path.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot",{})["value"]));return path.relative_to(ROOT).as_posix()
    try:
        b.navigate(args.url);b.call("WebDriver:SetWindowRect",{"width":1440,"height":950})
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
        origin=b.script("return performance.timeOrigin;")
        click("start-level")
        b.until("return performance.timeOrigin!=="+str(origin)+"&&document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
        click("open-workspace")
        assert "第三方库仅开放 NumPy" in b.script("return document.getElementById('learning-lesson').textContent;")
        if not b.script("return document.getElementById('learning-pane').hidden;"):click("close-learning")
        click("toggle-editor-logs")
        edit(algorithm()+"\nimport scipy\n");click("test-workspace")
        b.until("return document.getElementById('workspace-message').textContent.includes('DEPENDENCY_NOT_ALLOWED');")
        b.until("return document.getElementById('editor-runtime-log-view').textContent.includes('DEPENDENCY_NOT_ALLOWED');")
        edit(algorithm())
        edit('''import unittest
class FeedbackTest(unittest.TestCase):
    def test_feedback(self):
        print("test intermediate value", 42)
        self.assertEqual(1, 2, "player assertion")
''',"tests/test_numpy.py")
        if not b.script("return document.getElementById('editor-runtime-logs').hidden;"):click("toggle-editor-logs")
        failed=test();assert failed["status"]=="Failed",failed
        assert b.script("return document.getElementById('workspace-dialog').open;")
        assert failed["diagnostic"]["path"]=="tests/test_numpy.py",failed
        b.until("return !document.getElementById('editor-runtime-logs').hidden&&document.getElementById('workspace-message').textContent.includes('AssertionError');")
        failed_output=b.until("const text=document.getElementById('editor-runtime-log-view').textContent;return text.includes('Traceback (most recent call last):')&&text.includes('FAILED (failures=1)')&&text;")
        assert 'test intermediate value 42' in failed_output
        assert b.script("return [...document.querySelectorAll('#editor-runtime-log-view pre')].some(n=>n.textContent.includes('Traceback (most recent call last):')&&n.textContent.includes('AssertionError'));")
        failed_test_shot=screenshot("failed-test")
        edit(MATRIX_TEST,"tests/test_numpy.py")
        edit(algorithm(True))
        passed=test();assert passed["status"]=="Ready",passed
        b.until("return document.getElementById('editor-runtime-log-view').textContent.includes('matrix feedback');")
        deployment=deploy()
        b.until("return document.getElementById('editor-runtime-log-view').textContent.includes('runtime log demo');",timeout=15)
        b.until("return document.getElementById('deployment-state').textContent.includes('程序已停止');",timeout=15)
        click("finish-level");b.until("return !document.getElementById('open-workspace').disabled;")
        click("open-workspace")
        b.until("return [...document.querySelectorAll('#editor-runtime-log-view .runtime-log-entry button')].some(n=>n.textContent.includes('perception/transforms.py'));")
        b.script("[...document.querySelectorAll('#editor-runtime-log-view .runtime-log-entry button')].filter(n=>n.textContent.includes('perception/transforms.py')).at(-1).click();return true;")
        assert b.script("return document.getElementById('editor-path').textContent;")=="perception/transforms.py"
        assert "raise ValueError" in b.script("return document.querySelector('.cm-activeLine').textContent;")
        error_shot=screenshot("error")
        b.script("const filter=document.querySelector('#editor-runtime-log-view select');filter.value='test';filter.dispatchEvent(new Event('change'));return true;")
        labels=b.script("return [...document.querySelectorAll('#editor-runtime-log-view .runtime-log-entry small')].map(n=>n.textContent);")
        assert labels and all(label.startswith("测试快照") for label in labels),labels
        b.script("const filter=document.querySelector('#editor-runtime-log-view select');filter.value='all';filter.dispatchEvent(new Event('change'));document.querySelector('#editor-runtime-log-view .runtime-log-toolbar button').click();return true;")
        b.until("return document.getElementById('editor-runtime-log-view').dataset.count==='0';")
        edit(algorithm())
        origin=b.script("return performance.timeOrigin;")
        click("close-workspace");click("start-level")
        b.until("return performance.timeOrigin!=="+str(origin)+"&&document.getElementById('workspace-panel').dataset.ready==='true';",timeout=90)
        click("open-workspace")
        recovered=test();assert recovered["status"]=="Ready",recovered
        recovered_deployment=deploy()
        b.until("return document.getElementById('editor-runtime-log-view').textContent.includes('当前程序');")
        click("tab-logs")
        b.until("return document.getElementById('hud-runtime-log-view').textContent.includes('player feedback');")
        # Both backends use the ordinary authorized view; covariance stays flat only on JSON.
        b.script("window.__matrixView=null;(async()=>{const qa=window.wrappedJSObject?.tankbotQA??window.tankbotQA;window.__matrixView=qa?JSON.parse(await qa.view()):await (await fetch('/api/view')).json();})();return true;")
        view=b.until("return window.__matrixView?.payload.target_estimates?.length&&window.__matrixView;")
        assert view["payload"]["target_estimates"][0]["payload"]["covariance"]==[1,0,0,1]
        hud_shot=screenshot("hud")
        click("finish-level");b.until("return !document.getElementById('open-workspace').disabled;")
        click("open-workspace")
        if b.script("return document.getElementById('editor-runtime-logs').hidden;"):click("toggle-editor-logs")
        click("close-workspace")
        layouts=[]
        for width,height in ((1280,800),(500,740)):
            b.call("WebDriver:SetWindowRect",{"width":width,"height":height});click("open-workspace")
            layouts.append(b.script("const d=document.scrollingElement,o=document.querySelector('#editor-runtime-log-view .runtime-log-output');return {width:innerWidth,height:innerHeight,pageScroll:d.scrollHeight>d.clientHeight||d.scrollWidth>d.clientWidth,logHeight:o.clientHeight};"))
            click("close-workspace")
        assert all(not row["pageScroll"] and row["logHeight"]>20 for row in layouts),layouts
        report={"date":date.today().isoformat(),"url":args.url,"browser":b.capabilities["capabilities"]["browserVersion"],
                "static_rejection":True,"test_stdout_visible":True,"runtime_traceback_visible":True,"source_link_locates_line":True,
                "source_filter":True,"clear_display":True,"recovery":True,"covariance_wire_unchanged":True,
                "failed_test":failed,"native_unittest_output":True,"automatic_test_log_panel":True,
                "successful_deploy_closes_editor":True,"running_editor_locked":True,"finish_unlocks_editor":True,"failed_test_keeps_editor_open":True,
                "test":passed,"initial_deployment":deployment,"recovered_deployment":recovered_deployment,
                "layout":layouts,"screenshots":[failed_test_shot,error_shot,hud_shot]}
        paths=[p for directory in ("host/tankbot_host","runtime","sdk/python/tankbot","web") for p in (ROOT/directory).glob('*') if p.suffix in ('.py','.js','.html','.css')]
        paths.extend(ROOT/p for p in ("config/player-dependencies.yaml","tools/browser_runtime_feedback.py"))
        report["sources"]={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");print(args.output)
    finally:b.close()


if __name__=="__main__":main()
