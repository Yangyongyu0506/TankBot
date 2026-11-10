"""A small single-module filter replay lab. Private evaluator references never enter a worker."""
import copy
import json
import math
import platform
import sys
import time
from .engineering import settings
from .workspace import digest
from tankbot_protocol.validation import Validator,Rejected


def profile(authority):
    if authority.campaign:return authority.campaign.definition['evaluation'].get('experiment')
    return None


def diagnostic_policy(authority):
    declaration=profile(authority)
    if not declaration:return {}
    return {'channels':copy.deepcopy(declaration['diagnostics']),
            'max_events':settings()['lab']['diagnostic_max_events']}


def check_diagnostics(response,policy,module_ids):
    rows=response.get('payload',{}).get('telemetry',{}).get('diagnostics',[])
    counts={}
    for row in rows:
        mid=row['module_id'];name=row['name'];counts[mid]=counts.get(mid,0)+1
        if mid not in module_ids or name not in policy.get('channels',{}) or counts[mid]>policy.get('max_events',0):
            raise Rejected('UNAUTHORIZED')
        if len(row['values'])!=policy['channels'][name] or not all(type(v) in (int,float) and math.isfinite(v) for v in row['values']):
            raise Rejected('INVALID_SCHEMA')


class ExperimentLab:
    def __init__(self,authority):
        self.a=authority
        self.spec=profile(authority)
        self.limits=settings()['lab']
        self.record=None
        self.references={}  # Trusted sidecar, deliberately absent from export() and worker_init.
        self.recording=False
        self.reports=[]
        self.job=None
        self.counter=0
        self.bytes=0

    def enabled(self):
        if not self.spec or not self.a.campaign:return False
        vis=self.a.campaign.definition['permissions']['visualization']
        return (self.spec['metric'] in vis.get('allowed_metrics',[]) and 'target_estimates' in vis['allowed_layers']
                and set(self.spec['input_channels'])<=set(self.a.runtime_inputs()))

    def require(self):
        if not self.enabled():raise ValueError('EXPERIMENT_NOT_AUTHORIZED: 本关尚未开放传感器回放实验')

    def start(self):
        self.require()
        if self.job:raise ValueError('EXPERIMENT_BUSY')
        a=self.a;revision=getattr(a.worker,'revision',None)
        if revision is None or a.campaign.status!='active':raise ValueError('EXPERIMENT_NEEDS_DEPLOYMENT: 请先正式部署要录制的版本')
        previous=(self.record,self.references,self.reports,self.bytes)
        self.references={};self.reports=[];self.bytes=0
        self.record={'record_version':'1.0','kind':'sensor_replay','level_id':a.campaign.level_id,
            'run_id':a.run_id,'physics_hz':a.hz,'seed':a.config['runtime']['seed'],
            'recording_start_tick':a.tick,'attempt_start_tick':a.campaign.started_tick,
            'deployment_tick':(a.deployment.active or {}).get('activated_tick') if a.deployment else None,
            'source_revision':revision,'configuration_sha256':digest(a.config),
            'environment':{'python':sys.version,'platform':sys.platform,'machine':platform.machine(),
                'core_sha256':a.core.build_sha256,'runtime_packages':copy.deepcopy((a.worker.startup_result or {}).get('runtime_packages',{}))},
            'runtime_config':copy.deepcopy(a.worker_init['config']),
            'frames':[],'stop_reason':None,'failure':None,'bytes':0}
        active=a.deployment.active if a.deployment else None
        artifact=a.deployment.artifacts.get(active['sha256']) if active else None
        self.record['source_files']=copy.deepcopy(artifact['test_files'] if artifact else a.worker_init.get('sources',{}))
        if artifact:self.record['runtime_config']['module']=copy.deepcopy(artifact['module_config'])
        self.bytes=len(json.dumps(self.record,separators=(',',':')).encode())
        self.input_limit=self.limits['max_record_bytes']//2
        if self.bytes>=self.input_limit:
            self.record,self.references,self.reports,self.bytes=previous
            raise ValueError('EXPERIMENT_METADATA_LIMIT: 源码与元信息超过录制空间，请先导出项目或调整工程配额')
        self.record['bytes']=self.bytes
        self.recording=True
        return self.status()

    def stop(self,reason='user_stopped'):
        if self.recording:
            self.recording=False;self.record['stop_reason']=reason
        return self.status()

    def capture(self,request):
        if not self.recording:return
        if getattr(self.a.worker,'revision',None)!=self.record['source_revision']:
            self.stop('deployment_changed');return
        frame={'request':copy.deepcopy(request),'response':None,'error':None}
        # Inputs are the exact frozen request, not a view snapshot or full world state.
        if any(m['channel'] not in self.spec['input_channels'] for m in request['payload']['inputs']):
            self.stop('permission_changed');return
        size=len(json.dumps(frame,separators=(',',':')).encode())
        if len(self.record['frames'])>=self.limits['max_batches'] or self.bytes+size>self.input_limit:
            self.stop('capacity_reached');return
        self.record['frames'].append(frame);self.bytes+=size
        ticks={m['simulation_tick'] for m in request['payload']['inputs']}
        for tick in ticks:
            if self.a._target_history.get(tick) is not None:self.references[tick]=copy.deepcopy(self.a._target_history[tick])

    def complete(self,request,response,code):
        if self.record is None:return
        frame=next((f for f in reversed(self.record['frames']) if f['request']['request_id']==request['request_id']),None)
        if frame is None:return
        if code:
            frame['error']=code
            self.record['failure']={'tick':request['payload']['activation_tick'],'code':code,
                'logs':copy.deepcopy(self.a.logs.public())}
            self.stop('runtime_failure')
        else:
            frame['response']=copy.deepcopy(response)
        def size():
            for _ in range(2):self.record['bytes']=len(json.dumps(self.record,separators=(',',':'),allow_nan=False).encode())
            return self.record['bytes']
        if size()>self.limits['max_record_bytes']:
            self.stop('capacity_reached')
            self.record['stop_reason']='capacity_reached'
            for old in self.record['frames']:
                if old['response'] is not None:
                    old['response']=None;old['error']='RECORDED_OUTPUT_OMITTED_CAPACITY'
                    if size()<=self.limits['max_record_bytes']:break
            failure=self.record.get('failure')
            if failure:
                while failure['logs'].get('entries') and size()>self.limits['max_record_bytes']:
                    failure['logs']['entries'].pop(0)
                    failure['logs']['dropped']=failure['logs'].get('dropped',0)+1
            size()

    def import_record(self,value):
        self.require()
        if self.job or self.recording:raise ValueError('EXPERIMENT_BUSY')
        self.a.validator.structure(value,'experiment.schema.json')
        if len(value['frames'])>self.limits['max_batches'] or len(json.dumps(value,separators=(',',':')).encode())>self.limits['max_record_bytes']:raise ValueError('EXPERIMENT_RECORD_LIMIT')
        if value['level_id']!=self.a.campaign.level_id or value['physics_hz']!=self.a.hz:raise ValueError('EXPERIMENT_PROFILE_MISMATCH')
        # Imported input is validated against this level's grants, never treated as engine truth.
        validator=Validator(self.a.config,value['run_id'])
        previous=-1
        for frame in value['frames']:
            request=frame['request'];validator.structure(request)
            p=request['payload'];tick=p['activation_tick']
            if tick<=previous or p['output_commit_tick']-tick!=self.a.delay or len(p['modules'])!=1 or p['modules'][0]['module_id']!=self.a.contract['module_id']:
                raise ValueError('EXPERIMENT_TIME_OR_MODULE_MISMATCH')
            previous=tick
            for message in p['inputs']:
                channel=message['channel']
                if channel not in self.spec['input_channels'] or self.a.runtime_inputs().get(channel)!=message['schema']:
                    raise ValueError('EXPERIMENT_INPUT_DENIED')
                validator.structure(message)
                if message['run_id']!=value['run_id'] or not 0<=tick-message['simulation_tick']<=self.a.config['runtime']['input_max_age_ticks']:
                    raise ValueError('EXPERIMENT_INPUT_TIME_MISMATCH')
        expected=copy.deepcopy(self.a.worker_init['config']);expected['module']=value['runtime_config'].get('module')
        if value['runtime_config']!=expected:raise ValueError('EXPERIMENT_RUNTIME_CONFIG_MISMATCH')
        self.record=copy.deepcopy(value);self.references={};self.reports=[]
        return self.status()

    def export(self):
        self.require()
        if self.record is None:raise ValueError('EXPERIMENT_NO_RECORD')
        value=copy.deepcopy(self.record)
        value['recording']=self.recording
        return {'experiment_version':'1.0','record':value,'comparisons':copy.deepcopy(self.reports),
                'evaluation_reference_exported':False,'reimport_scoring':'新计算误差需要当前会话私有参考；导出文件不含真值。'}

    def compare(self,snapshot):
        self.require();a=self.a
        if self.recording or self.job or (a.deployment and a.deployment.job):raise ValueError('EXPERIMENT_BUSY')
        if not self.record or not self.record['frames']:raise ValueError('EXPERIMENT_NO_RECORD')
        if a.campaign.status=='active' and a.campaign.started_tick is not None:
            raise ValueError('EXPERIMENT_END_ATTEMPT_FIRST: 请先结束当前尝试，再比较版本')
        if len(self.reports)>=self.limits['max_comparisons']:raise ValueError('EXPERIMENT_COMPARE_LIMIT: 请清空比较或开始新录制')
        from .deployment import inspect_snapshot
        artifact=inspect_snapshot(snapshot,a)
        if 'graph' in artifact or any(p['schema']!=self.spec['output_schema'] for p in artifact['contract']['outputs'].values()):
            raise ValueError('EXPERIMENT_FILTER_ONLY: 控制器必须重建相同场景进行闭环评价')
        init=copy.deepcopy(a.worker_init);init.update(sources=artifact['files'],run_id=self.record['run_id'],
            reset_reason='sensor_replay',start_tick=max(0,self.record['frames'][0]['request']['payload']['activation_tick']-a.period))
        init['config']=copy.deepcopy(self.record['runtime_config']);init['config']['module']=copy.deepcopy(artifact['module_config'])
        init['contract']=copy.deepcopy(artifact['contract']);init['publisher_id']=a.publisher_id
        init['input_channels']=copy.deepcopy(a.input_channels);init['output_channels']=copy.deepcopy(a.output_channels)
        init['experiment_seed']=self.record['seed']
        worker=a.create_worker(init,deferred=True)
        self.job={'worker':worker,'artifact':artifact,'index':0,'phase':'booting','gate':None,
            'validator':Validator(a.config,self.record['run_id']),
            'report':{'revision':snapshot['revision'],'environment_sha256':artifact['environment'],
                'input_sha256':digest([f['request'] for f in self.record['frames']]),'status':'Running','points':[],
                'source_snapshot':copy.deepcopy(snapshot),'segments':[],'rmse_m':None,'scored_samples':0,'missing_intervals':[],'failure':None,'logs':[]}}
        return self.status()

    def clear(self):
        if self.job or self.recording:raise ValueError('EXPERIMENT_BUSY')
        self.reports=[]
        return self.status()

    def advance(self):
        self.counter+=1
        job=self.job
        if not job:return
        worker=job['worker']
        try:
            if job['phase']=='booting':
                if worker.fault:raise ValueError(worker.fault)
                if not worker.poll_ready():return
                job['phase']='submit'
            if job['phase']=='waiting':
                if self.counter<job['gate'] and not worker.fault:return
                response=worker.finish(controlled=self.a.controlled)
                if response is None:raise ValueError(worker.fault or 'MISSED_DEADLINE')
                frame=self.record['frames'][job['index']];request=frame['request'];tick=request['payload']['activation_tick']
                validator=job['validator'];validator.validate(response,now=request['payload']['output_commit_tick'],source_tick=tick,
                    grants={('runtime','/runtime/step','runtime_step_result@1',None)})
                if response['simulation_tick']!=tick:raise ValueError('INVALID_TIMESTAMP')
                if response['request_id']!=request['request_id'] or response['payload']['step_id']!=request['request_id']:
                    raise ValueError('EXPERIMENT_RESPONSE_MISMATCH')
                check_diagnostics(response,diagnostic_policy(self.a),[self.a.contract['module_id']])
                results=response['payload']['results']
                if results!=[{'module_id':self.a.contract['module_id'],'status':'completed','error_code':None}]:
                    raise ValueError('MODULE_ERROR')
                outputs=response['payload']['outputs']
                if len(outputs)>len(job['artifact']['contract']['outputs']) or len({m['channel'] for m in outputs})!=len(outputs):
                    raise ValueError('RATE_LIMITED')
                for output in outputs:
                    validator.validate(output,now=request['payload']['output_commit_tick'],source_tick=tick,
                        grants={(self.a.publisher_id,ch,self.spec['output_schema'],'map') for ch in self.a.output_channels.values()})
                if hasattr(worker,'timing'):worker.timing.decision(None,request['request_id'],accepted_status='replay_validated')
                self._point(job,frame,response)
                job['index']+=1;job['phase']='submit'
            if job['index']==len(self.record['frames']):self._finish('Completed');return
            if job['phase']=='submit':
                if not worker.submit(copy.deepcopy(self.record['frames'][job['index']]['request'])):
                    raise ValueError(worker.fault or 'EXPERIMENT_WORKER_BUSY')
                job['gate']=self.counter+self.a.delay;job['phase']='waiting'
        except (ValueError,Rejected,KeyError,TypeError) as error:
            if hasattr(worker,'timing'):worker.timing.decision(str(error),self.record['frames'][job['index']]['request']['request_id'])
            self._finish('Failed',str(error))

    def _point(self,job,frame,response):
        report=job['report'];request=frame['request'];tick=request['payload']['activation_tick']
        radar=next((m for m in request['payload']['inputs'] if m['schema']=='radar@1'),None)
        detections=radar['payload']['detections'] if radar else []
        outputs=response['payload']['outputs'];estimate=outputs[0] if outputs else None
        error=None
        if estimate and estimate['simulation_tick'] in self.references:
            reference=self.references[estimate['simulation_tick']]
            # Existing target history is a pose [x,y,yaw] or a target DTO, never sent to the candidate.
            position=reference['pose'] if isinstance(reference,dict) else reference
            error=math.hypot(estimate['payload']['x_m']-position[0],estimate['payload']['y_m']-position[1])
        point={'tick':tick,'time_s':tick/self.a.hz,'missing':not bool(detections),
            'measurements':copy.deepcopy(detections),'estimate':copy.deepcopy(estimate['payload']) if estimate else None,
            'estimate_sample_tick':estimate['simulation_tick'] if estimate else None,'error_m':error,
            'diagnostics':copy.deepcopy(response.get('payload',{}).get('telemetry',{}).get('diagnostics',[]))}
        report['points'].append(point)
        errors=[p['error_m'] for p in report['points'] if p['error_m'] is not None]
        report['scored_samples']=len(errors);report['rmse_m']=math.sqrt(sum(v*v for v in errors)/len(errors)) if errors else None
        point['cumulative_rmse_m']=report['rmse_m']
        base=self.record['frames'][0]['request']['payload']['activation_tick']
        groups={}
        for p in report['points']:
            groups.setdefault((p['tick']-base)//self.limits['segment_ticks'],[]).append(p)
        report['segments']=[{'start_tick':base+key*self.limits['segment_ticks'],'samples':len(points),
            'scored_samples':sum(p['error_m'] is not None for p in points),
            'rmse_m':math.sqrt(sum(p['error_m']**2 for p in points if p['error_m'] is not None)/sum(p['error_m'] is not None for p in points)) if any(p['error_m'] is not None for p in points) else None}
            for key,points in sorted(groups.items())]
        intervals=[]
        for p in report['points']:
            if not p['missing']:continue
            if intervals and intervals[-1]['end_tick']+self.a.period==p['tick']:intervals[-1]['end_tick']=p['tick']
            else:intervals.append({'start_tick':p['tick'],'end_tick':p['tick']})
        report['missing_intervals']=intervals

    def _finish(self,status,error=None):
        job=self.job
        if not job:return
        report=job['report'];worker=job['worker']
        report['status']=status
        if error:report['failure']={'frame_index':job['index'],'tick':self.record['frames'][min(job['index'],len(self.record['frames'])-1)]['request']['payload']['activation_tick'],'code':error}
        worker.close()
        report['logs']=copy.deepcopy(worker.logs.public()['entries'])
        report['timing']=worker.timing.public() if hasattr(worker,'timing') else None
        self.reports.append(report);self.job=None

    def status(self):
        if not self.enabled():return {'enabled':False,'kind':'sensor_replay','recording':False,'record':None,'frames':0,'comparisons':[],'job':None,'private_scoring_available':False,'limits':self.limits,'ui':settings()['ui']}
        return {'enabled':True,'kind':'sensor_replay','recording':self.recording,
            'record':None if self.record is None else {key:self.record[key] for key in ('source_revision','recording_start_tick','deployment_tick','seed','bytes','stop_reason','failure')},
            'frames':len(self.record['frames']) if self.record else 0,
            'comparisons':copy.deepcopy(self.reports),
            'job':None if not self.job else {'revision':self.job['report']['revision'],'phase':self.job['phase'],'completed_frames':self.job['index']},
            'private_scoring_available':bool(self.references),'limits':self.limits,'ui':settings()['ui']}

    def close(self):
        self.stop('session_closed')
        if self.job:self._finish('Cancelled','SESSION_CLOSED')
