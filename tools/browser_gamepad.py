#!/usr/bin/env python3
"""Exercise the actual browser input loop with simulated Gamepad API samples (not hardware certification)."""
import argparse
import base64
from datetime import date
import hashlib
import json
from pathlib import Path
import time
from browser_driver import Browser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",default="http://127.0.0.1:8765")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/reports/gamepad-native.json")
    args=parser.parse_args()
    b=Browser()
    # Execute in the page realm so its RAF loop sees the same navigator override.
    b.script=lambda source:b.call("WebDriver:ExecuteScript",{"script":source,"args":[],"newSandbox":False})["value"]
    settings=json.loads((ROOT/"config/m1.json").read_text())["view"]["gamepad"]
    def controls(axes=None,buttons=(),connected=True,mapping="standard"):
        value={"index":0,"id":"TankBot simulated standard controller","connected":connected,"mapping":mapping,
               "axes":axes or [0,0,0,0],"buttons":[{"pressed":False,"value":0} for _ in range(17)]}
        for name in buttons:value["buttons"][settings["buttons"][name]]={"pressed":True,"value":1}
        b.script("window.__joyPads="+json.dumps([value] if connected else [])+";return true;")
    def state():
        b.script("window.__joySnapshot=null;(async()=>{const qa=window.tankbotQA;window.__joySnapshot=qa?JSON.parse(await qa.view()):await(await fetch('/api/view')).json();})();return true;")
        return b.until("return window.__joySnapshot;")["payload"]
    def weapon(view):return next(row["payload"] for row in view["local_observations"] if row["schema"]=="weapon_state@1")
    def turret(view):return next(row["payload"]["position"][0] for row in view["local_observations"] if row["channel"]=="/robot/turret/joint_states")
    def pose(view):return view["selected_pose"]["pose"]
    def wait_state(predicate):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            value=state()
            if predicate(value):return value
            time.sleep(.05)
        raise AssertionError("Authorized state did not reach expected result: "+str(value))
    def status(value):b.until("return document.getElementById('gamepad-status').dataset.status==="+json.dumps(value)+";")
    def settle():
        return wait_state(lambda v:max(abs(x) for row in v["local_observations"] if row["channel"]=="/robot/sensors/joint_states" for x in row["payload"]["velocity"])<.02)
    evidence={}
    try:
        b.navigate(args.url);b.call("WebDriver:SetWindowRect",{"width":1280,"height":900})
        b.until("return document.getElementById('workspace-panel').dataset.ready==='true'&&document.getElementById('arena').dataset.robotVisible==='true';",timeout=90)
        b.script("document.getElementById('arena').focus();window.__joyPads=[];Object.defineProperty(navigator,'getGamepads',{configurable:true,value:()=>window.__joyPads});return true;")
        chassis=b.script("return document.getElementById('arena').dataset.chassis;")
        initial=state();shots=weapon(initial)["shots_fired"]
        controls([0,-1,0,0],('fire',));status('neutral')
        assert weapon(state())["shots_fired"]==shots
        controls();status('ready')
        start=pose(state());controls([0,-.7,0,0])
        driven=wait_state(lambda v:pose(v)["x_m"]-start["x_m"]>.2)
        evidence["forward_distance_m"]=pose(driven)["x_m"]-start["x_m"]
        controls();settle();start=pose(state());controls([-.7,0,0,0])
        if chassis=='omnidirectional':
            turned=wait_state(lambda v:pose(v)["y_m"]-start["y_m"]>.2)
            evidence["lateral_distance_m"]=pose(turned)["y_m"]-start["y_m"]
        else:
            turned=wait_state(lambda v:pose(v)["yaw_rad"]-start["yaw_rad"]>.2)
            evidence["yaw_change_rad"]=pose(turned)["yaw_rad"]-start["yaw_rad"]
        controls();settle();angle=turret(state());controls([0,0,-.7,0])
        rotated=wait_state(lambda v:turret(v)-angle>.2)
        evidence["turret_change_rad"]=turret(rotated)-angle
        controls();controls(buttons=('fire',))
        fired=wait_state(lambda v:weapon(v)["shots_fired"]==shots+1)
        time.sleep(.7)
        assert weapon(state())["shots_fired"]==shots+1
        evidence["single_shot_on_hold"]=True
        controls();status('ready');controls(buttons=('editor',))
        b.until("return document.getElementById('workspace-dialog').open;")
        parked=pose(settle())
        controls([0,-1,0,0],('fire',));status('paused')
        time.sleep(.3)
        still=pose(state())
        assert abs(still['x_m']-parked['x_m'])+abs(still['y_m']-parked['y_m'])<.01
        controls([0,-1,0,0],('fire','editor'))
        b.until("return !document.getElementById('workspace-dialog').open;")
        status('neutral');time.sleep(.3)
        assert weapon(state())["shots_fired"]==shots+1
        evidence["editor_blocks_motion_and_fire"]=True
        controls();status('ready');controls([0,-1,0,0])
        start=pose(state());wait_state(lambda v:pose(v)["x_m"]-start["x_m"]>.15)
        controls(connected=False);status('waiting');stopped=settle();location=pose(stopped)
        time.sleep(.35);after=pose(state())
        assert abs(after["x_m"]-location["x_m"])+abs(after["y_m"]-location["y_m"])<.01
        controls([0,-1,0,0],('fire',));status('neutral')
        assert weapon(state())["shots_fired"]==shots+1
        evidence["disconnect_brakes_and_reconnect_requires_neutral"]=True
        controls(mapping='');status('unsupported')
        b.script("Object.defineProperty(navigator,'getGamepads',{configurable:true,value:()=>{throw new DOMException('test','SecurityError');}});return true;")
        status('unavailable');start=pose(state())
        b.script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyW',bubbles:true}));return true;")
        wait_state(lambda v:pose(v)["x_m"]-start["x_m"]>.15)
        b.script("window.dispatchEvent(new KeyboardEvent('keyup',{code:'KeyW',bubbles:true}));Object.defineProperty(navigator,'getGamepads',{configurable:true,value:()=>window.__joyPads});return true;")
        controls();status('ready');settle();evidence["api_failure_preserves_keyboard"]=True
        controls([0,-1,0,0]);start=pose(state())
        wait_state(lambda v:pose(v)['x_m']-start['x_m']>.1)
        b.script("window.dispatchEvent(new Event('blur'));return true;")
        status('neutral');settle();controls();status('ready')
        evidence['blur_handler_requires_neutral']=True
        b.script("document.getElementById('gamepad-indicator').click();return true;")
        image=ROOT/".m1-cache"/(args.output.stem+'.png');image.write_bytes(base64.b64decode(b.call("WebDriver:TakeScreenshot",{})["value"]))
        dimensions=[]
        for width,height in ((1280,900),(500,740),(360,740)):
            b.call("WebDriver:SetWindowRect",{"width":width,"height":height})
            value=b.script("const d=document.scrollingElement;return {width:innerWidth,height:innerHeight,scrollWidth:d.scrollWidth,clientWidth:d.clientWidth,scrollHeight:d.scrollHeight,clientHeight:d.clientHeight};")
            assert value['scrollWidth']==value['clientWidth'] and value['scrollHeight']==value['clientHeight'],value
            dimensions.append(value)
        paths=['web/gamepad.js','web/app.js','web/index.html','web/style.css','config/m1.json','docs/schemas/gamepad-input.schema.json','tools/browser_gamepad.py']
        report={"date":date.today().isoformat(),"url":args.url,"input_source":"simulated Gamepad API; no physical controller certification",
                "browser":b.capabilities['capabilities']['browserVersion'],"chassis":chassis,"checks":evidence,"layout":dimensions,
                "screenshot":image.relative_to(ROOT).as_posix(),"sources":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(args.output)
    finally:b.close()


if __name__=='__main__':main()
