#!/usr/bin/env python3
"""独立的真实Firefox流程；自行创建并清理测试服务、工作区、存档及浏览器。"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))


from browser_support import port,stop


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('native','browser','both'),default='both')
    parser.add_argument('--scenario',choices=('engineering','path-tracking','global-planning','local-navigation'),default='engineering')
    parser.add_argument('--local-controller',choices=('geometric','dwa'),default='geometric')
    parser.add_argument('--planner',choices=('astar','dijkstra'),default='astar',help='Verification-only planning reference')
    parser.add_argument('--planning-faults',action='store_true',help='Also exercise isolated planning failures before the valid deployment')
    parser.add_argument('--seed',type=int,default=0,help='Isolated path-tracking scenario seed')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--firefox',default=shutil.which('firefox'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output is None:
        args.output=ROOT/('.m1-cache/navigation-c6-qa/browser' if args.scenario=='local-navigation' else '.m1-cache/navigation-c5-qa/browser' if args.scenario=='global-planning' else '.m1-cache/navigation-c4-qa/browser' if args.scenario=='path-tracking' else '.m1-cache/engineering-quality-20261104/browser')
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(),offline=args.offline)
    if not args.firefox:parser.error('需要Firefox和Marionette；普通组件测试请使用npm test')
    sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from tankbot_host.workspace_api import WorkspaceAPI
    from campaign_support import solutions,WINDOW
    import yaml
    base=load_config(ROOT/'config/game.yaml')
    if args.scenario=='path-tracking':base['campaign']['levels']['navigation.c4']['randomization']['seed']=args.seed
    if args.scenario=='global-planning':base['campaign']['levels']['navigation.c5']['randomization']['seed']=args.seed
    if args.scenario=='local-navigation':base['campaign']['levels']['navigation.c6']['randomization']['seed']=args.seed
    reports=[]
    for mode in ('native','browser') if args.mode=='both' else (args.mode,):
        directory=args.output.resolve()/mode/uuid.uuid4().hex;directory.mkdir(parents=True)
        config=json.loads(json.dumps(base));ui,runtime,marionette=port(),port(),port()
        config['host']['port']=ui;config['browser']['runtime_port']=runtime
        # A loaded profile can be serialized as an inline config for an isolated launcher.
        config_path=directory/'game.yaml';config_path.write_text(yaml.safe_dump(config,allow_unicode=True))
        initial_level='navigation.c5' if args.scenario=='local-navigation' else 'navigation.c4' if args.scenario=='global-planning' else 'navigation.c3' if args.scenario=='path-tracking' else 'c2'
        course=configure(config,initial_level);store=directory/'workspace';api=WorkspaceAPI(course,directory=store)
        first=api.store.read()
        if args.scenario in ('path-tracking','global-planning','local-navigation'):
            if args.scenario=='local-navigation':from planning_support import solution
            elif args.scenario=='global-planning':from path_tracking_support import solution
            else:from navigation_support import solution
            reference=solution(course)
            preserved=('control/wheel_controller.py','localization/odometry.py','localization/ekf.py',
                       'navigation/path_follower.py' if args.scenario in ('global-planning','local-navigation') else 'navigation/waypoint_controller.py')
            if args.scenario=='local-navigation':preserved+=('navigation/global_planner.py','navigation/planning_geometry.py')
            reference_snapshot=api.store.edit(first['revision'],{**{name:reference[name] for name in preserved},'my_notes.py':'# preserved browser fixture\n'})
        else:
            from campaign_support import EMA
            # Verification-only covariance/innovation, not a solution added to player templates.
            tracker=EMA.replace('from tankbot import TargetEstimate','from tankbot import TargetEstimate, diagnostic\nimport numpy as np')
            tracker=tracker.replace('        return self.point','        if measurements and self.point is not None:\n            diagnostic("innovation", np.array([measurements[0].x_m-self.point.x_m, measurements[0].y_m-self.point.y_m], dtype=np.float64))\n        if self.point is not None:\n            self.point = TargetEstimate(self.point.x_m,self.point.y_m,np.eye(2,dtype=np.float64)*0.04)\n        return self.point')
            files=solutions(course)
            files['perception/tracker.py']=tracker
            a=api.store.edit(first['revision'],{k:v for k,v in files.items() if first['files'].get(k)!=v})
            b=api.store.edit(a['revision'],{'perception/tracker.py':WINDOW})
            api.store.edit(b['revision'],{'perception/tracker.py':tracker})
        settings=directory/'settings.yaml';settings.write_bytes((ROOT/'config/settings.yaml').read_bytes())
        progress={'version':1,'completed_levels':['c0','c1'],'current_level':'c2',
                  'completions':{i:{'completed_at':datetime.now(timezone.utc).isoformat()} for i in ('c0','c1')}}
        if args.scenario in ('path-tracking','global-planning','local-navigation'):
            completed=['c0','navigation.c0','navigation.c1','navigation.c2','navigation.c3']+(['navigation.c4','navigation.c5'] if args.scenario=='local-navigation' else ['navigation.c4'] if args.scenario=='global-planning' else [])
            progress.update(completed_levels=completed,current_level=initial_level,
                completions={i:{'completed_at':datetime.now(timezone.utc).isoformat()} for i in completed})
        save=directory/'progress.json';save.write_text(json.dumps(progress))
        profile=directory/'firefox';profile.mkdir();downloads=directory/'downloads';downloads.mkdir()
        prefs={'marionette.port':marionette,'browser.download.folderList':2,'browser.download.dir':str(downloads),
               'browser.helperApps.neverAsk.saveToDisk':'application/json','browser.download.always_ask_before_handling_new_types':False}
        (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+','+json.dumps(v)+');\n' for k,v in prefs.items()))
        processes=[];logs=[]
        try:
            for name,command in [('server',[sys.executable,'tools/tankbot.py','serve' if mode=='native' else 'browser','--config',str(config_path),'--level',initial_level,'--workspace-store',str(store),'--settings-file',str(settings),'--save-file',str(save),'--browser-qa',*(['--offline'] if args.offline else [])]),
                                 ('firefox',[args.firefox,'--headless','--no-remote','--marionette','--profile',str(profile)])]:
                log=(directory/(name+'.log')).open('w');logs.append(log)
                processes.append(subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=(os.name=='posix')))
            deadline=time.monotonic()+60
            while True:
                try:
                    with socket.create_connection(('127.0.0.1',marionette),timeout=.5):break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Firefox Marionette启动超时；见'+str(directory))
                    time.sleep(.1)
            report=directory/'result.json'
            script='tools/browser_navigation_planning.py' if args.scenario in ('global-planning','local-navigation') else 'tools/browser_navigation_path.py' if args.scenario=='path-tracking' else 'tools/browser_engineering.py'
            command=[sys.executable,script,'--url',f'http://127.0.0.1:{ui}/'+('?runtime=browser' if mode=='browser' else ''),'--port',str(marionette),'--mode',mode,'--output',str(report)]
            if args.scenario=='local-navigation':command+=['--local-controller',args.local_controller,'--seed',str(args.seed)]
            if args.scenario=='global-planning':command+=['--planner',args.planner,'--seed',str(args.seed)]
            if args.scenario=='global-planning' and args.planning_faults:command+=['--planning-faults']
            result=subprocess.run(command,cwd=ROOT)
            if result.returncode:return result.returncode
            if args.scenario=='local-navigation':
                # Read through immutable snapshot/ledger validation, without
                # unlocking/upgrading the project or moving HEAD after UI QA.
                restored=api.store.read(reference_snapshot['revision'])
                assert restored==reference_snapshot
                head=api.store.read()
                for name in preserved+('my_notes.py',):assert head['files'][name]==restored['files'][name]
                record=json.loads(report.read_text())
                record['immutable_revision_readback']=reference_snapshot['revision']
                report.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            reports.append(str(report))
        finally:
            for process in reversed(processes):stop(process)
            for log in logs:log.close()
    print(json.dumps({'passed':True,'reports':reports,'scenario':args.scenario,'scope':'Linux/Firefox local player UI; prerequisite progress is an isolated fixture'},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
