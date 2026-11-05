"""Bounded observational timing. It never grants CPU time or changes a commit decision."""
from collections import deque
import copy
import math
import time
from .engineering import settings


def distribution(values):
    values=sorted(v for v in values if type(v) in (int,float) and math.isfinite(v) and v>=0)
    def percentile(p):return values[max(0,math.ceil(len(values)*p)-1)] if values else None
    return {'count':len(values),'p50_ms':percentile(.5),'p95_ms':percentile(.95),'p99_ms':percentile(.99),'max_ms':max(values,default=None)}


class RuntimeTiming:
    def __init__(self, budget_ms, backend):
        self.limits=settings()['timing']
        self.budget_ms=budget_ms
        self.backend=backend
        self.samples=deque(maxlen=self.limits['max_batches'])
        self.active=None
        self.total_batches=0

    def begin(self,request,started=None):
        p=request.get('payload',{});p=p if isinstance(p,dict) else {}
        started=time.monotonic() if started is None else started
        self.active={'step_id':request['request_id'],'activation_tick':p.get('activation_tick'),
            'commit_tick':p.get('output_commit_tick'),'sample_ticks':sorted({m['simulation_tick'] for m in p.get('inputs',[]) if isinstance(m,dict) and type(m.get('simulation_tick')) is int}),
            'modules':[m['module_id'] for m in p.get('modules',[]) if isinstance(m,dict) and isinstance(m.get('module_id'),str)], 'started_monotonic_s':started,
            'received_monotonic_s':None,'commit_monotonic_s':None,'status':'pending','failure_location':None}
        self.total_batches+=1

    def sent(self,**values):
        if self.active:self.active.update({k:v for k,v in values.items() if self.valid(v)})

    @staticmethod
    def valid(value):return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1000000

    def received(self,response,received=None,**transport):
        if self.active is None:return
        received=time.monotonic() if received is None else received
        item=self.active
        item.update(received_monotonic_s=received,round_trip_ms=max(0,(received-item['started_monotonic_s'])*1000))
        item.update({key:value for key,value in transport.items() if self.valid(value)})
        # This runs before Authority validates an untrusted response. Diagnostics
        # must never crash the reader or turn malformed input into an accepted result.
        payload=response.get('payload') if isinstance(response,dict) else None
        payload=payload if isinstance(payload,dict) else {}
        telemetry=payload.get('telemetry')
        telemetry=telemetry if isinstance(telemetry,dict) else {}
        transport=telemetry.get('transport')
        transport=transport if isinstance(transport,dict) else {}
        item.update({key:value for key,value in transport.items() if key in ('worker_decode_ms','runtime_python_ms','worker_encode_previous_ms') and self.valid(value)})
        if isinstance(transport.get('worker_encode_previous_step_id'),str):item['worker_encode_previous_step_id']=transport['worker_encode_previous_step_id'][:128]
        modules=[]
        costs=telemetry.get('modules')
        for row in costs[:64] if isinstance(costs,list) else []:
            if not isinstance(row,dict) or row.get('module_id') not in item['modules']:continue
            modules.append({key:value for key,value in row.items() if key=='module_id' or self.valid(value)})
        item['module_costs']=modules
        results=payload.get('results')
        results=results if isinstance(results,list) else []
        item['module_failures']=[r.get('module_id') for r in results[:64] if isinstance(r,dict) and r.get('status')=='failed']

    def finish(self,code=None,location=None):
        if self.active is None:return
        item,self.active=self.active,None
        now=time.monotonic();item['commit_monotonic_s']=now
        item['status']=code or ('MODULE_ERROR' if item.get('module_failures') else 'response')
        item['failure_location']=location or ('module_update' if item.get('module_failures') else None)
        if item['received_monotonic_s'] is not None:item['gate_wait_ms']=max(0,(now-item['received_monotonic_s'])*1000)
        else:item['elapsed_to_failure_ms']=max(0,(now-item['started_monotonic_s'])*1000)
        self.samples.append(item)

    def decision(self,code,step_id,accepted_status="committed"):
        if self.samples and self.samples[-1]['step_id']==step_id:
            row=self.samples[-1]
            location=row['failure_location']
            if code and location is None:location='module_update' if row.get('module_failures') else 'authority_validation'
            row.update(status=code or accepted_status,failure_location=location)

    def public(self):
        rows=list(self.samples)
        keys=('round_trip_ms','request_encode_ms','request_write_ms','response_decode_ms','gate_wait_ms',
              'runtime_python_ms','worker_decode_ms','worker_encode_previous_ms','bridge_round_trip_ms','elapsed_to_failure_ms')
        timeouts=sum(row['status'] in ('RESOURCE_LIMIT','MISSED_DEADLINE') for row in rows)
        modules={}
        for row in rows:
            for module in row.get('module_costs',[]):
                for key in ('input_decode_ms','update_ms','output_build_ms'):
                    if key in module:modules.setdefault(module['module_id'],{}).setdefault(key,[]).append(module[key])
        return {'backend':self.backend,'budget_ms':self.budget_ms,'observational_only':True,
            'window_capacity':self.limits['max_batches'],'total_batches':self.total_batches,'window_batches':len(rows),
            'timeouts':timeouts,'timeout_rate':timeouts/len(rows) if rows else 0.,
            'costs':{key:distribution([r[key] for r in rows if key in r]) for key in keys},
            'modules':{mid:{key:distribution(v) for key,v in costs.items()} for mid,costs in modules.items()},
            'recent':copy.deepcopy(rows[-self.limits['max_public_samples']:]),
            'active':copy.deepcopy(self.active)}
