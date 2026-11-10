#!/usr/bin/env python3
"""只校准可信的合成负载迭代数；不调整任何玩家运行 profile。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'host')]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',choices=('native','pyodide'),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--cpu-affinity')
    p.add_argument('--offline',action='store_true');args=p.parse_args()
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(),offline=args.offline)
    from runtime_budget_support import benchmark_options
    options=benchmark_options(ROOT/'config/runtime-benchmark.yaml')['calibration']
    n=options['initial_iterations'][args.backend];rounds=[]
    for number in range(options['max_rounds']):
        output=args.output/f'round-{number}'
        command=[sys.executable,str(ROOT/'tools/benchmark_runtime.py'),'--backend',args.backend,'--workloads','near_cap',
            '--deadlines','80','--conditions','foreground','--batches-per-cell',str(options['batches_per_round']),
            '--slice-attempts','--output',str(output),'--iterations',str(n),*(['--offline'] if args.offline else []),
            *(['--cpu-affinity',args.cpu_affinity] if args.cpu_affinity else [])]
        subprocess.run(command,cwd=ROOT,check=True)
        report=json.loads(next(output.glob('*/summary.json')).read_text())
        median=report['result']['costs']['batch_module_update_ms']['p50_ms']
        rounds.append({'iterations':n,'update_median_ms':median,'report':str(next(output.glob('*/summary.json')).relative_to(args.output))})
        if median is None or median<=0:raise RuntimeError('Calibration did not observe measurable completed updates')
        if abs(median-options['target_update_ms'])<=options['target_update_ms']*options['relative_tolerance']:break
        if number+1<options['max_rounds']:
            n=max(options['min_iterations'],min(options['max_iterations'],round(n*options['target_update_ms']/median)))
    result={'schema_version':'1.0','backend':args.backend,'iterations':n,'target_update_ms':options['target_update_ms'],
            'rounds':rounds,'budget_changed':False,'wall_time_not_cpu':True}
    (args.output/'calibration.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
