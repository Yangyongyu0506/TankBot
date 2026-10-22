#!/usr/bin/env python3
"""Real Firefox M2 probe. Requires a browser launcher and Firefox --marionette already running."""
import argparse
import json
import hashlib
import platform
from pathlib import Path
import time
from browser_driver import Browser


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8765/?runtime=browser")
    parser.add_argument("--inspect",action="store_true")
    parser.add_argument("--expect-fault",action="store_true")
    parser.add_argument("--expect-weapons",action="store_true")
    parser.add_argument("--ticks",type=int,default=600)
    parser.add_argument("--output",type=Path,default=Path("docs/reports/m2-browser.json"))
    args=parser.parse_args();b=Browser()
    try:
        b.navigate(args.url)
        b.script("window.__m2Frames=[];window.__m2Start=performance.now();function collect(t){window.__m2Frames.push(t);if(window.__m2Frames.length>4000)window.__m2Frames.shift();requestAnimationFrame(collect);}requestAnimationFrame(collect);return true;")
        state=b.until("return /在线|失败/.test(document.getElementById('connection').textContent) && document.getElementById('connection').textContent;",timeout=90)
        print(state,flush=True)
        if args.inspect:return
        assert "失败" not in state,state
        b.script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyW',bubbles:true}));return true;")
        b.until("return Number(document.getElementById('arena').dataset.runtimeTick)>60;")
        b.script("window.dispatchEvent(new KeyboardEvent('keyup',{code:'KeyW',bubbles:true}));return true;")
        b.until(f"return Number(document.getElementById('arena').dataset.runtimeTick)>={args.ticks};",timeout=60)
        health=b.script("return JSON.parse(document.getElementById('arena').dataset.runtimeHealth);")
        assert bool(health["runtime_fault"])==args.expect_fault,health
        assert health["fixed_commit_gates"],health
        if args.expect_weapons:assert health["shots_fired"]>0,health
        if not args.expect_fault:
            assert health["pose_commits"]>=90,health
            assert not health["rejections"],health
            assert len(health.get("fixtures",[]))==49,"Run server with --browser-qa"
            for record in health["fixtures"]:assert record["verdict"]==record["expected"],record
            if health.get("security"):assert all(health["security"].values()),health["security"]
        frames=b.script("return window.__m2Frames;")
        gaps=sorted(b-a for a,b in zip(frames,frames[1:]))
        from datetime import date
        capabilities=b.capabilities["capabilities"]
        report={"browser":{k:capabilities[k] for k in ("browserName","browserVersion","platformName","moz:buildID","moz:headless")},"date":date.today().isoformat(),"health":health,"expect_fault":args.expect_fault,
                "display":{"frames":len(frames),"gap_p50_ms":gaps[len(gaps)//2],"gap_p95_ms":gaps[int(len(gaps)*.95)],"gap_max_ms":max(gaps)},
                "ui":b.script("return {model:document.getElementById('arena').dataset.model,x:document.getElementById('x').textContent,connection:document.getElementById('connection').textContent};")}
        root=Path(__file__).resolve().parents[1]
        report["os"]=platform.platform()
        paths=["config/m1.json","config/browser-assets.lock.json","Cargo.lock","target/wasm32-unknown-unknown/release/tankbot_core.wasm","build/browser/authority-bundle.json","build/browser/player-bundle.json"]
        report["artifacts"]={p:{"bytes":(root/p).stat().st_size,"sha256":hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in paths}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        print(args.output)
    finally:b.close()


if __name__=="__main__":main()
