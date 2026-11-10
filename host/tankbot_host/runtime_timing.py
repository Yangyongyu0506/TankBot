"""Bounded, untrusted observations; deadlines are enforced by the Supervisors."""
from collections import deque
import copy
import math
import time
import uuid
from .engineering import settings


def distribution(values):
    values=sorted(v for v in values if type(v) in (int,float) and math.isfinite(v) and v>=0)
    def percentile(p):return values[max(0,math.ceil(len(values)*p)-1)] if values else None
    return {'count':len(values),'p50_ms':percentile(.5),'p95_ms':percentile(.95),
            'p99_ms':percentile(.99),'p99_9_ms':percentile(.999),'max_ms':max(values,default=None)}


class RuntimeTiming:
    def __init__(self, budget_ms, backend, *, profile=None):
        self.limits=settings()['timing']
        self.budget_ms=budget_ms  # Compatibility: this diagnostic alias means wall deadline only.
        self.backend=backend
        self.profile=copy.deepcopy(profile)
        self.samples=deque(maxlen=self.limits['max_batches'])
        self.journal=deque(maxlen=self.limits['max_journal_events'])
        self.journal_sequence=0
        self.journal_dropped=0
        self.timing_id=uuid.uuid4().hex
        self.active=None
        self.total_batches=0

    def begin(self,request,started=None,*,started_ns=None):
        p=request.get('payload',{});p=p if isinstance(p,dict) else {}
        if started_ns is None:started_ns=time.monotonic_ns() if started is None else round(started*1_000_000_000)
        self.active={'step_id':request['request_id'],'activation_tick':p.get('activation_tick'),
            'commit_tick':p.get('output_commit_tick'),'sample_ticks':sorted({m['simulation_tick'] for m in p.get('inputs',[]) if isinstance(m,dict) and type(m.get('simulation_tick')) is int}),
            'modules':[m['module_id'] for m in p.get('modules',[]) if isinstance(m,dict) and isinstance(m.get('module_id'),str)],
            'phase':'first_activation' if self.total_batches==0 else 'steady',
            'started_monotonic_ns':started_ns,'started_monotonic_s':started_ns/1_000_000_000,
            'deadline_monotonic_ns':started_ns+round(self.budget_ms*1_000_000),
            'received_monotonic_s':None,'commit_monotonic_s':None,'status':'pending','failure_location':None}
        self.total_batches+=1

    def sent(self,*,step_id=None,**values):
        if self.active and (step_id is None or step_id==self.active['step_id']):
            self.active.update({k:v for k,v in values.items() if self.valid(v)})

    @staticmethod
    def valid(value):return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1000000

    def received(self,response,received=None,*,received_ns=None,**transport):
        if self.active is None:return
        if received_ns is None:received_ns=time.monotonic_ns() if received is None else round(received*1_000_000_000)
        item=self.active
        item.update(received_monotonic_ns=received_ns,received_monotonic_s=received_ns/1_000_000_000,
                    round_trip_ms=max(0,(received_ns-item['started_monotonic_ns'])/1_000_000))
        for key in ('response_decode_ms','bridge_round_trip_ms','response_delivery_ms'):
            if self.valid(transport.get(key)):item[key]=transport[key]
        if type(transport.get('response_decode_started_monotonic_ns')) is int:
            item['response_decode_started_monotonic_ns']=transport['response_decode_started_monotonic_ns']
        # Worker telemetry is never consulted for a deadline or authorization decision.
        payload=response.get('payload') if isinstance(response,dict) else None
        payload=payload if isinstance(payload,dict) else {}
        telemetry=payload.get('telemetry')
        telemetry=telemetry if isinstance(telemetry,dict) else {}
        costs=telemetry.get('transport')
        costs=costs if isinstance(costs,dict) else {}
        item.update({key:value for key,value in costs.items() if key in ('worker_decode_ms','runtime_python_ms','worker_encode_previous_ms') and self.valid(value)})
        if isinstance(costs.get('worker_encode_previous_step_id'),str):item['worker_encode_previous_step_id']=costs['worker_encode_previous_step_id'][:128]
        modules=[]
        costs=telemetry.get('modules')
        for row in costs[:64] if isinstance(costs,list) else []:
            if not isinstance(row,dict) or row.get('module_id') not in item['modules']:continue
            if any(m['module_id']==row['module_id'] for m in modules):continue
            modules.append({key:value for key,value in row.items() if key=='module_id' or (key in ('input_decode_ms','update_ms','output_build_ms') and self.valid(value))})
        item['module_costs']=modules
        if modules and all('update_ms' in m for m in modules):
            item['batch_module_update_ms']=sum(m['update_ms'] for m in modules)
        results=payload.get('results')
        results=results if isinstance(results,list) else []
        item['module_failures']=[r.get('module_id') for r in results[:64] if isinstance(r,dict) and isinstance(r.get('module_id'),str) and r.get('status')=='failed']

    def _event(self,kind,row):
        self.journal_sequence+=1
        if len(self.journal)==self.journal.maxlen:self.journal_dropped+=1
        self.journal.append({'event':kind,'sequence':self.journal_sequence,'timing_id':self.timing_id,**copy.deepcopy(row)})

    def drain(self):
        """A benchmark persists these deltas, rather than repeatedly exporting a sliding window."""
        rows=[]
        for _ in range(len(self.journal)):
            try:rows.append(self.journal.popleft())
            except IndexError:break
        return {'events':rows,'timing_id':self.timing_id,'sequence':self.journal_sequence,'dropped_events':self.journal_dropped}

    def finish(self,code=None,location=None,*,at_gate=False):
        if self.active is None:return
        item,self.active=self.active,None
        now=time.monotonic_ns();item['finished_monotonic_ns']=now
        if at_gate:
            item['commit_monotonic_ns']=now;item['commit_monotonic_s']=now/1_000_000_000
        item['status']=code or ('MODULE_ERROR' if item.get('module_failures') else 'response')
        item['failure_location']=location or ('module_update' if item.get('module_failures') else None)
        if at_gate and 'received_monotonic_ns' in item:item['gate_wait_ms']=max(0,(now-item['received_monotonic_ns'])/1_000_000)
        if 'received_monotonic_ns' not in item:item['elapsed_to_failure_ms']=max(0,(now-item['started_monotonic_ns'])/1_000_000)
        item['censored']='received_monotonic_ns' not in item
        self.samples.append(item)
        self._event('batch_finish',item)

    def decision(self,code,step_id,accepted_status="committed"):
        if self.samples and self.samples[-1]['step_id']==step_id:
            row=self.samples[-1]
            location=row['failure_location']
            if code and location is None:location='module_update' if row.get('module_failures') else 'authority_validation'
            now=time.monotonic_ns()
            row.update(status=code or ('MODULE_ERROR' if row.get('module_failures') else accepted_status),failure_location=location,commit_monotonic_ns=now,commit_monotonic_s=now/1_000_000_000)
            if 'received_monotonic_ns' in row:row['gate_wait_ms']=max(0,(now-row['received_monotonic_ns'])/1_000_000)
            self._event('batch_decision',row)

    def public(self):
        rows=list(self.samples)
        keys=('round_trip_ms','response_arrival_ms','request_encode_ms','request_queue_ms','request_write_ms','response_decode_ms','response_delivery_ms','gate_wait_ms',
              'runtime_python_ms','batch_module_update_ms','worker_decode_ms','worker_encode_previous_ms','bridge_round_trip_ms','elapsed_to_failure_ms')
        wall=sum(row['status']=='RESOURCE_LIMIT' and row['failure_location'] in ('wall_deadline','response_decode_deadline') for row in rows)
        gates=sum(row['status']=='MISSED_DEADLINE' for row in rows)
        timeouts=wall+gates
        modules={}
        for row in rows:
            for module in row.get('module_costs',[]):
                for key in ('input_decode_ms','update_ms','output_build_ms'):
                    if key in module:modules.setdefault(module['module_id'],{}).setdefault(key,[]).append(module[key])
        return {'backend':self.backend,'budget_ms':self.budget_ms,'batch_wall_deadline_ms':self.budget_ms,
            'execution_profile':copy.deepcopy(self.profile),'observational_only':True,'clock':'monotonic_ns',
            'window_capacity':self.limits['max_batches'],'total_batches':self.total_batches,'window_batches':len(rows),
            'journal_sequence':self.journal_sequence,'journal_dropped_events':self.journal_dropped,
            'timeouts':timeouts,'wall_timeouts':wall,'missed_commit_gates':gates,'timeout_rate':timeouts/len(rows) if rows else 0.,
            'costs':{key:distribution([r[key] for r in rows if key in r]) for key in keys},
            'modules':{mid:{key:distribution(v) for key,v in costs.items()} for mid,costs in modules.items()},
            'recent':copy.deepcopy(rows[-self.limits['max_public_samples']:]),'active':copy.deepcopy(self.active)}
