#!/usr/bin/env python3
"""Private M1b evaluator; never import this into the player worker or serve its output."""
import copy
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'protocol'),str(ROOT/'sdk/python')]
from tankbot_host.authority import Authority,CoreAdapter,load_config
from measure_m1 import distribution,digest


def measure(config,name):
    c=copy.deepcopy(config);c['scene']['default_chassis']=name
    c['control_sources'].update(turret='robot',weapon='robot')
    c['module']['entry_point']='weapon_demo:WeaponDemo';c['module']['weapon_demo']['enabled']=True
    started=time.monotonic();a=Authority(c,controlled=True);cold=(time.monotonic()-started)*1000
    try:
        for _ in range(c['validation']['ticks']):a.advance()
        replay=CoreAdapter(c,name)
        try:
            for record in a.replay:replay.call(record['actuators'])
            exact=replay.snapshot==a._private
        finally:replay.close()
        rejected=[e for e in a.audit if e['event']=='rejected']
        if rejected or not exact:raise RuntimeError('M1b closed loop acceptance failed')
        return {'chassis':name,'ticks':a.tick,'cold_start_ms':cold,'host_tick_ms':distribution(a.tick_times_ms),
                'worker_round_trip_ms':distribution(a.worker.batch_times_ms),'max_view_bytes':a.max_view_bytes,
                'weapon_state':a._private['weapon_state'],'target_hits':a._private['target_hits'],
                'relative_angle_rad':a._private['turret_state']['relative_angle_rad'],
                'same_build_all_actuator_replay_exact':exact,'rejections':rejected}
    finally:a.close()


def main():
    config=load_config(ROOT/'config/game.yaml')
    core=CoreAdapter(config,config['scene']['default_chassis'])
    try:
        out=core.call({'op':'step','fire_requests':[{'publisher_id':'measure','request_id':'one','source_tick':0}]})
        while not any(e['kind']=='bounce' for e in out['weapon_events']):out=core.call({'op':'step'})
        bounce=next(e for e in out['weapon_events'] if e['kind']=='bounce')
        wall=config['scene']['walls'][bounce['wall_index']]
        p=config['weapons']['projectile'];muzzle=config['weapons']['turret']['muzzle_offset_m'][0]
        expected=(wall['center'][0]-wall['size'][0]/2-p['radius_m']-muzzle)/p['relative_speed_mps']
        toi_error=abs(bounce['time_s']-expected)
        speed_error=abs(abs(out['projectiles'][0]['velocity'][0])-p['relative_speed_mps'])
        if toi_error>config['weapons']['numerics']['time_epsilon_s'] or speed_error>config['validation']['numeric_tolerance']:
            raise RuntimeError('Wall sweep measurement failed')
        native=core.call({'op':'weapons_probe','config':config})
    finally:core.close()
    wasm=json.loads(subprocess.check_output(['node',str(ROOT/'tools/wasm_probe.mjs')],cwd=ROOT))
    equal=(wasm['shots_fired']==native['weapon_state']['shots_fired'] and wasm['relative_angle_rad']==native['relative_angle_rad'])
    if not equal:raise RuntimeError('Native/WASM weapon probe mismatch')
    report={'date':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),'os':platform.platform(),'python':platform.python_version(),
            'native_binary_sha256':digest(ROOT/'target/debug/core_worker'),'config_sha256':digest(ROOT/'config/game.yaml'),
            'cargo_lock_sha256':digest(ROOT/'Cargo.lock'),'wasm_sha256':digest(ROOT/'target/wasm32-unknown-unknown/debug/tankbot_core.wasm'),
            'scene':{'dynamic_bodies':2,'static_walls':len(config['scene']['walls']),'static_targets':len(config['weapons']['targets'])},
            'wall_toi_absolute_error_s':toi_error,'wall_reflection_speed_absolute_error_mps':speed_error,
            'impact_gate_max_delay_s':config['solver']['dt'],'native_weapon_probe':native,'wasm_probe':wasm,
            'native_wasm_weapon_probe_equal':equal,'runs':[measure(config,n) for n in config['chassis']]}
    path=ROOT/'docs/reports/m1b-current-profile.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(path.relative_to(ROOT))


if __name__=='__main__':main()
