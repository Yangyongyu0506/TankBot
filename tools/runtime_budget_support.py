"""Bounded timing journal and isolated verification sources for runtime-budget benchmarks."""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot_host.runtime_timing import distribution


def benchmark_options(path):
    from tankbot_host.configuration import load_yaml
    from jsonschema import Draft202012Validator
    value=load_yaml(path)
    schema=json.loads((ROOT/'docs/schemas/runtime-benchmark.schema.json').read_text())
    Draft202012Validator(schema).validate(value)
    c=value['calibration']
    if not c['min_iterations']<=min(c['initial_iterations'].values())<=max(c['initial_iterations'].values())<=c['max_iterations']:
        raise ValueError('BENCHMARK_CALIBRATION_RANGE')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class ArtifactGuard:
    """Check between attempts, outside measured batches; never pool a changing build."""
    def __init__(self,paths):
        self.hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
        self.sha256=digest(self.hashes)

    def check(self):
        changed=[p for p,value in self.hashes.items() if not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=value]
        if changed:raise RuntimeError('BENCHMARK_ARTIFACT_CHANGED: '+', '.join(Path(p).name for p in changed[:8]))


def sources(config,kind,iterations):
    if kind=='path':
        from path_tracking_support import solution
        files=solution(config)
    elif kind=='ekf':
        from weapons_curriculum_support import solutions
        files=solutions(config)
    else:
        from weapons_support import solutions
        files=solutions(config)
    if kind in ('empty','controlled_compute','infinite'):
        body={'empty':'return None','infinite':'while True: pass','controlled_compute':
              'accumulator = 0.0\n        for index in range('+str(iterations)+'):\n            accumulator += (index % 97) * 0.0001\n        return None'}[kind]
        files['perception/tracker.py']='class Tracker:\n    def update(self, measurements, dt):\n        '+body+'\n'
    return files


class Journal:
    """Bounded on disk and in memory; every received delta is persisted, including failures."""
    def __init__(self,directory,limits):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.limits=limits;self.part=0;self.size=0;self.file=None;self.events=0
        self.pending={};self.rows=[];self.attempts=[];self.dropped=0;self.sequences={};self.drops={}

    def write(self,value):
        raw=json.dumps(value,separators=(',',':'),allow_nan=False)+'\n'
        size=len(raw.encode())
        if self.file is None or self.size+size>self.limits['max_jsonl_part_bytes']:
            if self.file:self.file.close()
            self.part+=1
            if self.part>self.limits['max_jsonl_parts']:raise RuntimeError('BENCHMARK_STORAGE_LIMIT')
            self.file=(self.directory/f'events-{self.part:04d}.jsonl').open('x',encoding='utf-8')
            self.size=0
        self.file.write(raw);self.file.flush();self.size+=size;self.events+=1

    def ingest(self,snapshot):
        timing=snapshot['timing']
        identity=timing.get('timing_id',snapshot['run_id'])
        self.drops[identity]=max(self.drops.get(identity,0),timing['dropped_events']);self.dropped=sum(self.drops.values())
        for event in timing['events']:
            previous=self.sequences.get(event['timing_id'],0)
            if event['sequence']<=previous:continue  # End-of-attempt polling is idempotent.
            self.sequences[event['timing_id']]=event['sequence']
            event={**event,'run_id':snapshot['run_id']};self.write(event)
            key=(event['timing_id'],event['step_id'])
            if event['event']=='batch_finish':self.pending[key]=event
            elif event['event']=='batch_decision':
                self.pending.pop(key,None);self._row(event)
        if len(self.pending)>self.limits['max_summary_batches']:raise RuntimeError('BENCHMARK_PENDING_LIMIT')

    def _row(self,row):
        if len(self.rows)>=self.limits['max_summary_batches']:raise RuntimeError('BENCHMARK_SUMMARY_LIMIT')
        self.rows.append(row)

    def end_attempt(self,snapshot,reason,*,startup_ms=None):
        self.ingest(snapshot)
        for key,row in list(self.pending.items()):
            if row['run_id']==snapshot['run_id']:
                self._row(row);self.pending.pop(key)
        failures=[r for r in self.rows if r['run_id']==snapshot['run_id'] and r['status'] in ('RESOURCE_LIMIT','MISSED_DEADLINE')]
        row={'event':'attempt_end','run_id':snapshot['run_id'],'tick':snapshot['tick'],
             'status':snapshot['attempt_status'],'reason':reason,'runtime_fault':snapshot['runtime_fault'],
             'runtime_deadline_failure':bool(failures or snapshot['runtime_fault'] in ('RESOURCE_LIMIT','MISSED_DEADLINE')),
             'startup_ms':startup_ms,'result':snapshot.get('result')}
        self.attempts.append(row);self.write(row)

    def summary(self):
        rows=self.rows
        # Each row already contains a sum from the SAME batch, never a sum of p99s.
        stages=('round_trip_ms','response_arrival_ms','runtime_python_ms','batch_module_update_ms','worker_decode_ms','worker_encode_previous_ms',
                'request_encode_ms','request_queue_ms','request_write_ms','response_decode_ms','gate_wait_ms','bridge_round_trip_ms','elapsed_to_failure_ms')
        def costs(subset):return {k:distribution([r[k] for r in subset if k in r]) for k in stages}
        deadlines=sum(r['status']=='RESOURCE_LIMIT' and r['failure_location'] in ('wall_deadline','response_decode_deadline') for r in rows)
        gates=sum(r['status']=='MISSED_DEADLINE' for r in rows)
        full=[a for a in self.attempts if a['reason'] not in ('sample_target','harness_interrupted','calibration_slice')]
        failed=sum(a['runtime_deadline_failure'] for a in full)
        # Wilson interval: the sample size is complete attempts, not correlated batches.
        n=len(full);z=1.959963984540054
        if n:
            p=failed/n;den=1+z*z/n;centre=(p+z*z/(2*n))/den
            half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;interval=[max(0,centre-half),min(1,centre+half)]
        else:interval=None
        modules={}
        for r in rows:
            for m in r.get('module_costs',[]):
                for k in ('input_decode_ms','update_ms','output_build_ms'):
                    if k in m:modules.setdefault(m['module_id'],{}).setdefault(k,[]).append(m[k])
        return {'batches':len(rows),'responses':sum('round_trip_ms' in r for r in rows),
                'censored_batches':sum(r.get('censored',False) for r in rows),
                'statuses':dict(Counter(r['status'] for r in rows)),
                'failure_locations':dict(Counter(r['failure_location'] for r in rows if r.get('failure_location'))),
                'wall_timeouts':deadlines,'wall_timeout_rate':deadlines/len(rows) if rows else None,
                'missed_commit_gates':gates,'missed_gate_rate':gates/len(rows) if rows else None,
                'attempts':len(self.attempts),'complete_attempts':n,'runtime_failed_complete_attempts':failed,
                'runtime_complete_attempt_failure_rate':failed/n if n else None,'attempt_failure_wilson_95':interval,
                'costs':costs(rows),'phases':{phase:costs([r for r in rows if r['phase']==phase]) for phase in ('first_activation','steady')},
                'modules':{mid:{k:distribution(v) for k,v in costs.items()} for mid,costs in modules.items()},
                'startup':distribution([a['startup_ms'] for a in self.attempts if a.get('startup_ms') is not None]),
                'journal_events':self.events,'dropped_events':self.dropped,
                'zero_resolution_note':'0 ms is a quantized observation, not zero CPU cost',
                'attempt_results':self.attempts}

    def close(self):
        if self.file:self.file.close()


def machine():
    import importlib.metadata
    cpu=None
    if Path('/proc/cpuinfo').exists():
        cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),None)
    return {'os':platform.system(),'release':platform.release(),'architecture':platform.machine(),'cpu':cpu,
            'cpu_affinity':sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
            'python':sys.version,'packages':{p:importlib.metadata.version(p) for p in ('numpy','jsonschema','PyYAML')}}
