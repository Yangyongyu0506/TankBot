#!/usr/bin/env python3
"""从有界JSONL逐批重建统计；保留原始记录，不将窗口或旧直方图改阈值。"""
import argparse
from collections import Counter,defaultdict
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('sdk/python','host','protocol','tools')]
from runtime_budget_support import Journal,digest
from tankbot_host.runtime_timing import distribution
from tankbot_host.configuration import load_yaml


def normalize_event(original):
    row=copy.deepcopy(original)
    # Early R1 observers labeled already-late, UNDECODED bytes as a full RTT.
    # Recover the actual arrival observation without inventing the missing decode.
    if (row.get('failure_location')=='wall_deadline' and row.get('received_monotonic_ns') is not None
            and 'response_decode_ms' not in row and 'round_trip_ms' in row):
        row['response_arrival_ms']=row.pop('round_trip_ms')
        row['response_arrival_monotonic_ns']=row.pop('received_monotonic_ns')
        row['received_monotonic_s']=None;row.pop('gate_wait_ms',None);row['censored']=True
        row['analysis_normalization']='late_undecoded_arrival'
    return row


def read_cell(directory,limits):
    collector=Journal(directory,limits)
    collector.write=lambda event:None  # Analysis is strictly read-only.
    parts=[];normalizations=0;gaps=0;previous={}
    for path in sorted(directory.glob('events-*.jsonl')):
        if path.stat().st_size>limits['max_jsonl_part_bytes']:raise ValueError('BENCHMARK_PART_SIZE_LIMIT: '+str(path))
        parts.append({'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        with path.open() as stream:
            for number,line in enumerate(stream,1):
                if len(line.encode())>limits['max_jsonl_part_bytes']:raise ValueError('BENCHMARK_LINE_LIMIT')
                try:event=json.loads(line)
                except ValueError as error:raise ValueError(f'{path.name}:{number}: incomplete JSONL; preserve as interrupted evidence') from error
                kind=event['event']
                if kind in ('batch_finish','batch_decision'):
                    normalized=normalize_event(event)
                    normalizations+=kind=='batch_finish' and 'analysis_normalization' in normalized
                    identity=event['timing_id'];seq=event['sequence'];last=previous.get(identity,0)
                    if seq>last+1:gaps+=seq-last-1
                    previous[identity]=max(last,seq)
                    collector.ingest({'run_id':event['run_id'],'timing':{'events':[normalized],'dropped_events':0}})
                elif kind=='attempt_end':
                    collector.end_attempt({'run_id':event['run_id'],'tick':event['tick'],'attempt_status':event['status'],
                        'runtime_fault':event['runtime_fault'],'result':event.get('result'),
                        'timing':{'events':[],'dropped_events':0}},event['reason'],startup_ms=event.get('startup_ms'))
    # A process interruption never creates a successful trial out of its unfinished batch.
    for row in collector.pending.values():collector._row(row)
    result=collector.summary()
    result['costs']['response_delivery_ms']=distribution([r['response_delivery_ms'] for r in collector.rows if 'response_delivery_ms' in r])
    for phase,costs in result['phases'].items():
        costs['response_delivery_ms']=distribution([r['response_delivery_ms'] for r in collector.rows if r['phase']==phase and 'response_delivery_ms' in r])
    original=json.loads((directory/'summary.json').read_text()) if (directory/'summary.json').exists() else {}
    result['dropped_events']=max(gaps,original.get('result',{}).get('dropped_events',0))
    result.update(late_arrival_normalizations=normalizations,raw_parts=parts,complete_source_file=bool(original))
    terminal=[a for a in collector.attempts if a['status']!='active']
    aborted=[a for a in collector.attempts if a['reason']=='runtime_failure' and a['status']=='active']
    result['course_terminal_attempts']=len(terminal)
    result['course_outcomes']=dict(Counter((a.get('result') or {}).get('reason') for a in terminal))
    result['runtime_aborted_active_course_trials']=len(aborted)
    result['attempt_metric_scope']='planned full-horizon trials; a runtime abort is a failed trial, not a forged course result'
    browser=original.get('result',{}).get('browser')
    if browser:
        caps=browser.get('capabilities',{}).get('capabilities',{})
        result['browser']={'name':caps.get('browserName'),'version':caps.get('browserVersion'),
            'platform':caps.get('platformName'),'headless':caps.get('moz:headless'),
            'visibility':browser.get('visibility'),'harness':browser.get('harness')}
    return original.get('metadata',json.loads((directory/'metadata.json').read_text())),result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'.m1-cache/runtime-profile-matrix')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    limits=load_yaml(ROOT/'config/runtime-benchmark.yaml')['limits']
    cells=[];totals=defaultdict(lambda:{'batches':0,'wall_timeouts':0,'missed_gates':0,'trials':0,'runtime_failed_trials':0})
    comparisons=defaultdict(lambda:{'builds':set(),'runtime_sources':set(),'algorithm_sources':set(),'seeds':set()})
    for directory in sorted({p.parent for p in args.input.glob('**/metadata.json')}):
        metadata,result=read_cell(directory,limits);case=metadata['case'];key=(case['backend'],case['workload'])
        entry=totals[key]
        for name,value in [('batches',result['batches']),('wall_timeouts',result['wall_timeouts']),('missed_gates',result['missed_commit_gates']),
                           ('trials',result['complete_attempts']),('runtime_failed_trials',result['runtime_failed_complete_attempts'])]:entry[name]+=value
        compare=comparisons[key]
        for label,field in [('builds','build_sha256'),('runtime_sources','runtime_sources_sha256'),('algorithm_sources','source_revision_sha256')]:compare[label].add(metadata[field])
        compare['seeds'].add(metadata['seed'])
        sanitized={k:v for k,v in metadata.items() if k!='machine'}
        sanitized['machine']=metadata['machine']
        sanitized['config_sha256_kind']=metadata.get('config_sha256_kind','prepared source config before ephemeral port assignment (R1)')
        cells.append({'cell':str(directory.relative_to(args.input)),'metadata':sanitized,'result':result})
    lock=json.loads((ROOT/'config/browser-assets.lock.json').read_text())
    runtime_lock=json.loads((ROOT/'build/browser/pyodide/pyodide-lock.json').read_text())
    profiles=load_yaml(ROOT/'config/runtime-profiles.yaml')
    report={'report_version':'1.0','analysis_version':'1.1','counts_from':'unique timing_id + step_id in raw JSONL, including cancelled/censored batches',
        'primary_workload_minimum_applies_to':'each backend/workload total across measured conditions and actual watchdog candidates; not 10000 per cell',
        'selected_defaults':{backend:{'profile_id':identity,'module_declared_budget_cap_ms':profiles['module_declared_budget_cap_ms'],**profiles['profiles'][identity]}
                            for backend,identity in profiles['defaults'].items()},
        'runtime_browser':{'pyodide_version':lock['version'],'lock_sha256':hashlib.sha256((ROOT/'config/browser-assets.lock.json').read_bytes()).hexdigest(),
                           'interpreter_build':runtime_lock['info'],'numpy':runtime_lock['packages']['numpy']['version'],
                           'jsonschema':runtime_lock['packages']['jsonschema']['version']},
        'scope_notes':['Actual platform, CPU, dependencies, browser version and document visibility are recorded per cell',
            'Requested process affinity is not an OS isolation guarantee; thermal, child-process placement and OS effects are not eliminated',
            'Runtime-only page keeps authorized view/health traffic; full canvas/editor flow is tested separately',
            'Weapons trials intentionally do not fire: their ordinary course outcome is timeout, not a gameplay pass',
            'Runtime failure aborts a planned horizon; active courses are explicitly distinguished from actual course terminal results',
            'R1 late pre-decode arrivals are normalized as censored, not complete RTT observations; raw bytes are unchanged',
            'Selected defaults remain experimental; zero failures and 10000 batches are not a <1% reliability guarantee'],
        'totals':{backend+'.'+workload:value for (backend,workload),value in totals.items()},
        'comparability':{backend+'.'+workload:{k:sorted(v) for k,v in values.items()} for (backend,workload),values in comparisons.items()},
        'cells':cells,'reliability_guarantee':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'cells':len(cells),'batches':sum(c['result']['batches'] for c in cells),
        'late_arrival_normalizations':sum(c['result']['late_arrival_normalizations'] for c in cells),'output':str(args.output)},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
