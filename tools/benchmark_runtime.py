#!/usr/bin/env python3
"""隔离、可恢复的真实 Runtime 截止基准；不重放旧传感器冒充闭环。"""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),*[str(ROOT/p) for p in ('sdk/python','host','protocol','tests','tools')]]


def atomic_json(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def native_run(config,files,case,directory,limits,target,slice_attempts,guard):
    from tankbot_host.authority import Authority
    from tankbot_host.runtime_benchmark import snapshot
    from runtime_budget_support import Journal
    journal=Journal(directory,limits);began=time.monotonic();reason=None
    try:
        for attempt in range(limits['max_attempts_per_cell']):
            guard.check()
            startup=time.monotonic();a=Authority(config,startup_sources=files,startup_is_deployment=True)
            startup_ms=(time.monotonic()-startup)*1000
            journal.write({'event':'attempt_start','run_id':a.run_id,'attempt':attempt,'profile':a.runtime_profile.public(),
                           'startup_ms':startup_ms,'runtime_packages':a.worker.startup_result.get('runtime_packages',{})})
            deadline=time.monotonic();poll=deadline;latest=None
            try:
                while True:
                    now=time.monotonic()
                    if now<deadline:time.sleep(deadline-now);continue
                    catchup=0
                    while time.monotonic()>=deadline and catchup<config['host']['max_catchup_ticks']:
                        a.advance()
                        if case['host_load_ms'] and a.tick%a.period==1:
                            until=time.monotonic_ns()+round(case['host_load_ms']*1_000_000)
                            while time.monotonic_ns()<until:pass
                        deadline+=1/a.hz;catchup+=1
                        if a.worker.fault or (a.campaign and a.campaign.status!='active'):break
                    if time.monotonic()>=deadline:deadline=time.monotonic()+1/a.hz
                    terminal=bool(a.worker.fault or (a.campaign and a.campaign.status!='active'))
                    if terminal or time.monotonic()>=poll:
                        latest=snapshot(a);journal.ingest(latest);poll=time.monotonic()+limits['poll_seconds']
                    if terminal:reason='runtime_failure' if a.worker.fault else 'task_terminal';break
                    if (slice_attempts or not case['primary']) and len(journal.rows)+len(journal.pending)>=target:
                        reason='sample_target';break
                    if time.monotonic()-began>limits['max_cell_seconds']:reason='cell_time_limit';break
            finally:
                a.close();latest=snapshot(a);journal.end_attempt(latest,reason or 'harness_interrupted',startup_ms=startup_ms)
            guard.check()
            if len(journal.rows)>=target or reason=='cell_time_limit':break
        return journal.summary()
    finally:journal.close()


class BrowserRun:
    def __init__(self,config,files,directory,options):
        self.logs=[];self.process=None;self.server=None;self.browser=None;self.threads=[]
        from tankbot_host.browser_server import BrowserServer
        from tankbot_host.application import ApplicationState
        from tankbot_host.workspace_api import WorkspaceAPI
        from browser_driver import Browser
        from browser_support import port,stop
        self.stop=stop;self.logs=[];self.process=None;self.server=None;self.browser=None;self.threads=[]
        self.config=config;self.directory=directory
        marionette=port()
        # Progress and source fixtures live only in this cell directory.
        application=ApplicationState(config,directory/'settings.yaml',directory/'progress.json')
        current=config['campaign']['active_level']
        completed=list(config['campaign']['levels'])  # Explicit progress fixture, never a normal save.
        application.write(application.progress_path,{'version':1,'completed_levels':completed,'current_level':current,
            'completions':{i:{'completed_at':'2026-11-06T00:00:00+00:00'} for i in completed}})
        application.read_progress()
        self.server=BrowserServer(config,workspace_store=directory/'workspace',application=application)
        original=self.server.ui.RequestHandlerClass
        class BenchmarkHandler(original):
            def do_GET(self):
                if self.path!='/__runtime-budget.html':return super().do_GET()
                raw=(ROOT/'tools/fixtures/runtime-benchmark.html').read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
                self.end_headers();self.wfile.write(raw)
        self.server.ui.RequestHandlerClass=BenchmarkHandler
        # This is a trusted fixture, not a caller-provided Runtime message.
        self.server.ui_json['/deployment.json']=files
        api=self.server.workspace;head=api.store.read()
        api.store.edit(head['revision'],{k:v for k,v in files.items() if head['files'].get(k)!=v})
        self.threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (self.server.ui,self.server.runtime)]
        for t in self.threads:t.start()
        profile=directory/'firefox';profile.mkdir();prefs={'marionette.port':marionette}
        (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+','+json.dumps(v)+');\n' for k,v in prefs.items()))
        log=(directory/'firefox.log').open('w');self.logs.append(log)
        self.process=subprocess.Popen([options.firefox,*(['--headless'] if not options.headed else []),'--no-remote','--marionette','--profile',str(profile)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name=='posix')
        import socket
        until=time.monotonic()+options.browser_options['startup_timeout_s']
        while True:
            try:
                with socket.create_connection(('127.0.0.1',marionette),timeout=.5):break
            except OSError:
                if time.monotonic()>until:raise RuntimeError('Firefox startup timeout')
                time.sleep(.1)
        self.browser=Browser(marionette)
        self.browser.call('WebDriver:SetWindowRect',{'width':options.browser_options['width'],'height':options.browser_options['height']})
        self.browser.navigate(f'http://127.0.0.1:{config["host"]["port"]}/__runtime-budget.html')
        self.browser.until('return !!(window.wrappedJSObject?.tankbotQA??window.tankbotQA);',options.browser_options['startup_timeout_s'])
        self.environment={'capabilities':self.browser.capabilities,'headed':options.headed,
            'harness':'focused Runtime-only page; authorized view/health traffic retained, game canvas disabled',
            'visibility':self.browser.script('return {visibility:document.visibilityState,focus:document.hasFocus(),userAgent:navigator.userAgent};')}

    def request(self,value):
        self.browser.script("window.__budgetReply=null;(async()=>{try{window.__budgetReply=JSON.parse(await(window.wrappedJSObject?.tankbotQA??window.tankbotQA).post('/api/benchmark',"+json.dumps(value)+"));}catch(e){window.__budgetReply={ok:false,error:String(e)};}})();return true;")
        result=self.browser.until('return window.__budgetReply;',30)
        if not result['ok']:raise RuntimeError('Benchmark QA request: '+str(result))
        return result['value']

    def close(self):
        if self.browser:
            try:self.browser.close()
            except (OSError,RuntimeError,EOFError):pass
        if self.process:self.stop(self.process)
        if self.server:
            for s in (self.server.ui,self.server.runtime):s.shutdown();s.server_close()
            for t in self.threads:t.join(timeout=5)
        for log in self.logs:log.close()


def browser_run(config,files,case,directory,limits,target,slice_attempts,options,guard):
    from runtime_budget_support import Journal
    journal=Journal(directory,limits);runner=None;began=time.monotonic()
    try:
        guard.check()
        runner=BrowserRun.__new__(BrowserRun)
        runner.__init__(config,files,directory,options)
        journal.write({'event':'preparation','snapshot':runner.request({'operation':'drain'}),'browser':runner.environment})
        for attempt in range(limits['max_attempts_per_cell']):
            guard.check()
            startup=time.monotonic()
            latest=runner.request({'operation':'restart','host_load_ms':case['host_load_ms']})
            run_id=latest['run_id'];journal.ingest(latest)
            while not latest['ready'] and not latest['runtime_fault']:
                if time.monotonic()-startup>options.browser_options['startup_timeout_s']:raise RuntimeError('Robot startup timeout')
                time.sleep(limits['poll_seconds']);latest=runner.request({'operation':'drain'});journal.ingest(latest)
            startup_ms=(time.monotonic()-startup)*1000
            journal.write({'event':'attempt_start','attempt':attempt,'run_id':run_id,'profile':latest['profile'],
                           'startup_ms':startup_ms,'runtime_packages':(latest['startup_result'] or {}).get('runtime_packages',{})})
            while True:
                if latest['runtime_fault'] or latest['attempt_status']!='active':reason='runtime_failure' if latest['runtime_fault'] else 'task_terminal';break
                if (slice_attempts or not case['primary']) and len(journal.rows)+len(journal.pending)>=target:reason='sample_target';break
                if time.monotonic()-began>limits['max_cell_seconds']:reason='cell_time_limit';break
                time.sleep(limits['poll_seconds']);latest=runner.request({'operation':'drain'});journal.ingest(latest)
            journal.end_attempt(latest,reason,startup_ms=startup_ms)
            guard.check()
            if len(journal.rows)>=target or reason=='cell_time_limit':break
        summary=journal.summary();summary['browser']=runner.environment
        return summary
    finally:
        if runner:runner.close()
        journal.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('native','pyodide','all'),default='all')
    parser.add_argument('--output',type=Path,default=ROOT/'.m1-cache/runtime-profiles-20261106')
    parser.add_argument('--config',type=Path,default=ROOT/'config/runtime-benchmark.yaml')
    parser.add_argument('--workloads',nargs='+');parser.add_argument('--deadlines',nargs='+',type=int)
    parser.add_argument('--conditions',nargs='+');parser.add_argument('--batches-per-cell',type=int)
    parser.add_argument('--slice-attempts',action='store_true',help='Only a short smoke/calibration slice; never an entire-attempt reliability trial')
    parser.add_argument('--resume',action='store_true');parser.add_argument('--plan',action='store_true')
    parser.add_argument('--iterations',type=int,help='Trusted controlled-compute calibration value, frozen across candidates')
    parser.add_argument('--calibration-file',type=Path,help='Use a previously measured, frozen synthetic workload calibration')
    parser.add_argument('--firefox',default=shutil.which('firefox'));parser.add_argument('--headed',action='store_true')
    parser.add_argument('--cpu-affinity',help='Linux only: comma-separated CPU IDs inherited by all isolated child processes')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(),offline=args.offline)
    if args.cpu_affinity:
        if not hasattr(os,'sched_setaffinity'):parser.error('CPU affinity is unavailable on this platform')
        cpus={int(v) for v in args.cpu_affinity.split(',')}
        if not cpus or not cpus<=os.sched_getaffinity(0):parser.error('CPU affinity must be a subset of the current allowed set')
        os.sched_setaffinity(0,cpus)
    from tankbot_host.configuration import load_yaml
    from tankbot_host.authority import load_config
    from tankbot_host.campaign import configure
    from runtime_budget_support import digest,machine,sources,benchmark_options,ArtifactGuard
    options=benchmark_options(args.config);args.browser_options=options['browser']
    if options['schema_version']!='1.0':parser.error('Unsupported benchmark version')
    output=args.output.resolve()
    if not (output.is_relative_to(ROOT/'.m1-cache') or output.is_relative_to(Path('/tmp'))):parser.error('Output must be isolated under .m1-cache or /tmp')
    output.mkdir(parents=True,exist_ok=True)
    base=load_config(ROOT/'config/game.yaml');base['browser']['probe_enabled']=True
    backends=('native','pyodide') if args.backend=='all' else (args.backend,)
    workloads=args.workloads or list(options['workloads']);conditions=args.conditions or list(options['conditions'])
    if set(workloads)-set(options['workloads']) or set(conditions)-set(options['conditions']):parser.error('Unknown workload/condition')
    if any(options['workloads'][name]['kind']=='controlled_compute' for name in workloads) and not (args.calibration_file or args.iterations or args.plan):
        parser.error('near_cap requires a frozen calibration: run tools/calibrate_runtime_benchmark.py, then pass --calibration-file')
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for folder,pattern in [('host','*.py'),('runtime','*.py'),('protocol','*.py'),('sdk/python','*.py'),('web','*.js'),('templates','*.py')]
            for p in (ROOT/folder).rglob(pattern)}
    environment=machine();reports=[];plan=[]
    guarded=[ROOT/p for p in hashes]
    for folder,pattern in [('config','*.yaml'),('levels','*.yaml'),('assets/maps','*.yaml'),('docs/schemas','*.json')]:
        guarded+=list((ROOT/folder).rglob(pattern))
    guarded += [ROOT/p for p in ('tools/benchmark_runtime.py','tools/runtime_budget_support.py','tools/browser_support.py',
        'tools/fixtures/runtime-benchmark.html','requirements.txt','config/browser-assets.lock.json')]
    guarded += [p for p in (ROOT/'target/debug/core_worker',ROOT/'target/wasm32-unknown-unknown/release/tankbot_core.wasm',
                            ROOT/'build/browser/authority-bundle.json',ROOT/'build/browser/player-bundle.json') if p.exists()]
    guard=ArtifactGuard(guarded)
    for backend in backends:
        calibration=json.loads(args.calibration_file.read_text()) if args.calibration_file else None
        if calibration and calibration['backend']!=backend:parser.error('Calibration backend mismatch')
        iterations=args.iterations or (calibration['iterations'] if calibration else options['calibration']['initial_iterations'][backend])
        for name in workloads:
            workload=options['workloads'][name]
            for wall in args.deadlines or options['candidates_ms'][backend]:
                for condition in conditions:
                    case={'backend':backend,'workload':name,'kind':workload['kind'],'primary':workload['primary'],
                          'wall_ms':wall,'condition':condition,'host_load_ms':options['conditions'][condition]['host_load_ms']}
                    count=args.batches_per_cell or workload.get('batches',options['batches_per_cell'][backend])
                    if not 1<=count<=options['limits']['max_summary_batches']:parser.error('Invalid batch target')
                    case['target_batches']=count;case['slice_attempts']=args.slice_attempts
                    config=configure(base,workload['level']);config['runtime']['seed']=options['seed']
                    config['campaign']['levels'][workload['level']]['randomization']['seed']=options['seed']
                    catalog=config['runtime']['profiles'];identity=catalog['defaults'][backend]
                    catalog['profiles'][identity]['batch_wall_deadline_ms']=wall
                    if backend=='pyodide' and not args.plan:
                        from browser_support import port
                        config['host']['port']=port();config['browser']['runtime_port']=port()
                    from tankbot_host.scene_definition import resolve_scene
                    config=resolve_scene(config).to_config()
                    reproducible=copy.deepcopy(config)
                    reproducible['host']['port']=None;reproducible['browser']['runtime_port']=None
                    files=sources(config,workload['kind'],iterations)
                    binary=ROOT/('target/debug/core_worker' if backend=='native' else 'target/wasm32-unknown-unknown/release/tankbot_core.wasm')
                    metadata={'schema_version':'1.0','metadata_version':'1.2','case':case,'machine':environment,'seed':options['seed'],
                        'artifact_guard_sha256':guard.sha256,
                        'source_revision_sha256':digest(files),'runtime_sources_sha256':digest(hashes),
                        'config_sha256':digest(config),'config_sha256_kind':'resolved effective config, including isolated transport ports',
                        'scenario_sha256':digest(reproducible),
                        'benchmark_driver_sha256':digest({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                            ('tools/benchmark_runtime.py','tools/runtime_budget_support.py','tools/browser_support.py','tools/fixtures/runtime-benchmark.html')}),
                        'build_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'build_mode':'debug' if backend=='native' else 'release',
                        'controlled_iterations':iterations if workload['kind']=='controlled_compute' else None,
                        'profile':{**catalog['profiles'][identity],'profile_id':identity,'module_declared_budget_cap_ms':catalog['module_declared_budget_cap_ms']}}
                    metadata['identity_sha256']=digest({**metadata,'config_sha256':metadata['scenario_sha256']})
                    key=f'{backend}-{name}-{wall}ms-{condition}';plan.append({'cell':key,'target_batches':count,'identity':metadata['identity_sha256']})
                    if args.plan:continue
                    directory=output/key;path=directory/'summary.json'
                    if path.exists() and args.resume:
                        old=json.loads(path.read_text())
                        if old['metadata']['identity_sha256']!=metadata['identity_sha256']:raise RuntimeError('BENCHMARK_RESUME_IDENTITY_MISMATCH: '+key)
                        reports.append(str(path.relative_to(output)));continue
                    if directory.exists():raise RuntimeError('BENCHMARK_CELL_EXISTS: use --resume or a new output directory: '+str(directory))
                    directory.mkdir();atomic_json(directory/'metadata.json',metadata)
                    print(json.dumps({'event':'cell_start','cell':key,'target_batches':count}),flush=True)
                    try:
                        result=native_run(config,files,case,directory,options['limits'],count,args.slice_attempts,guard) if backend=='native' else browser_run(config,files,case,directory,options['limits'],count,args.slice_attempts,args,guard)
                        report={'metadata':metadata,'result':result,'complete':result['batches']>=count and result['dropped_events']==0,
                                'finished_at':datetime.now(timezone.utc).isoformat()}
                        atomic_json(path,report);reports.append(str(path.relative_to(output)))
                        atomic_json(output/'index.json',{'schema_version':'1.0','reports':reports,'planned':plan,'reliability_guarantee':False})
                        print(json.dumps({'event':'cell_end','cell':key,'batches':result['batches'],
                            'wall_timeouts':result['wall_timeouts'],'missed_gates':result['missed_commit_gates'],
                            'attempts':result['attempts'],'complete':report['complete']}),flush=True)
                    except BaseException as error:
                        atomic_json(directory/'interruption.json',{'error':type(error).__name__+': '+str(error),'metadata':metadata})
                        raise
    if args.plan:print(json.dumps({'cells':plan,'target_batches':sum(c['target_batches'] for c in plan),'minimum_active_seconds':sum(c['target_batches'] for c in plan)/base['clock']['algorithm_hz']},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
