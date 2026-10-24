#!/usr/bin/env python3
"""Private radial-omni acceptance report; never served to robots or the UI."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'protocol'),str(ROOT/'sdk/python')]
from tankbot_host.authority import Authority,CoreAdapter,load_config


def digest(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def main():
    config=load_config(ROOT/'config/game.yaml');config['scene']['default_chassis']='omnidirectional'
    a=Authority(config,controlled=True)
    max_position_error=max_yaw_error=0.0
    v=config['validation']['probe_target'][0];w=config['view']['keyboard_yaw_radps']
    target={'linear':{'x':v,'y':v,'z':0},'angular':{'x':0,'y':0,'z':w}}
    try:
        for tick in range(config['validation']['ticks']):
            if tick%a.period==0:a.keyboard(target)
            a.advance();selected=a.view['payload']['selected_pose']
            if selected:
                truth=a.replay[selected['simulation_tick']]['truth_pose'];pose=selected['pose']
                max_position_error=max(max_position_error,math.hypot(pose['x_m']-truth[0],pose['y_m']-truth[1]))
                error=pose['yaw_rad']-truth[2]
                max_yaw_error=max(max_yaw_error,abs(math.atan2(math.sin(error),math.cos(error))))
        replay=CoreAdapter(config,'omnidirectional')
        try:
            for record in a.replay:replay.call(record['actuators'])
            exact=replay.snapshot==a._private
            native=replay.call({'op':'wheel_probe','config':config})
        finally:replay.close()
        rejections=[e for e in a.audit if e['event']=='rejected']
        commits=sum(e['event']=='pose_commit' for e in a.audit)
    finally:a.close()
    wasm=json.loads(subprocess.check_output(['node',str(ROOT/'tools/wasm_probe.mjs')],cwd=ROOT))
    difference=abs(wasm['omni_first_wheel_radps']-native[0])
    if not exact or rejections or not commits or max_position_error>config['validation']['odom_error_tolerance_m'] or difference>config['validation']['numeric_tolerance']:
        raise SystemExit('Radial omni acceptance failed')
    report={'date':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),'platform':platform.platform(),
            'geometry':config['wheels'],'target':target,'ticks':config['validation']['ticks'],'pose_commits':commits,
            'max_position_error_m':max_position_error,'max_yaw_error_rad':max_yaw_error,'rejections':rejections,
            'same_build_replay_exact':exact,'native_wheel_rates_radps':native,'wasm_probe':wasm,
            'native_wasm_first_wheel_absolute_error_radps':difference,
            'config_sha256':digest('config/game.yaml'),'native_binary_sha256':digest('target/debug/core_worker'),
            'wasm_sha256':digest('target/wasm32-unknown-unknown/debug/tankbot_core.wasm')}
    path=ROOT/'docs/reports/omni-baseline.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(path.relative_to(ROOT))


if __name__=='__main__':main()
