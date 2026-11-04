"""Immutable sensor instances and the sole Authority-side sampling lifecycle."""
from dataclasses import dataclass
import copy
import random
import json


@dataclass(frozen=True)
class Mount2D:
    parent_frame: str
    x_m: float
    y_m: float
    yaw_rad: float


@dataclass(frozen=True)
class RandomStream:
    id: str
    seed_mode: str

    def seed(self, seed):
        return seed if self.seed_mode=='legacy_seed' else f'{seed}:{self.id}'


@dataclass(frozen=True)
class SensorInstance:
    id: str
    robot_id: str
    type: str
    backend: str
    mount: Mount2D
    period_ticks: int
    random_stream: RandomStream | None
    topic: str
    schema: str
    frame_id: str
    publisher_id: str
    parameters_json: str


def python_backend(sensor):
    from .level_plugins import SENSORS
    entry=SENSORS.get(sensor['type'])
    # Unknown types are reported by the shared structural validator, including
    # legacy standalone instances that are normalized before validation.
    return entry is not None and (entry[3] is None or (sensor['type']=='wheel_encoder' and bool(sensor.get('parameters'))))


def normalize_sensors(value, source):
    """Legacy rate/center fields are translated once; contradictions are rejected."""
    from .level_plugins import LevelValidationError,SENSORS
    hz=value['world']['simulation']['physics_hz']
    for robot_index,robot in enumerate(value['robots']):
        for index,s in enumerate(robot.get('sensors',[])):
            path=f'robots[{robot_index}].sensors[{index}]'
            def fail(field,reason):raise LevelValidationError(source,path+'.'+field,reason)
            if 'period_ticks' in s:
                period=s['period_ticks']
                if type(period) is not int or period<=0 or hz%period:fail('period_ticks','period must be a positive integer divisor of physics_hz')
                rate=hz//period
                if 'update_hz' in s and s['update_hz']!=rate:fail('update_hz','rate and period_ticks disagree')
                s['update_hz']=rate
            elif type(s.get('update_hz')) is int and s['update_hz']>0 and hz%s['update_hz']==0:
                s['period_ticks']=hz//s['update_hz']
            else:continue  # Schema supplies the existing precise rate error.
            p=s.get('parameters',{})
            s.setdefault('id',s['type']);s.setdefault('robot_id',robot['id'])
            s.setdefault('mount',{'parent_frame':'base_link','translation_m':p.get('mount_m',[0.,0.]),'yaw_rad':p.get('yaw_rad',0.)})
            if s['robot_id']!=robot['id']:fail('robot_id','sensor owner must match the containing robot')
            mount=s['mount']
            if not isinstance(mount,dict) or set(mount)!={'parent_frame','translation_m','yaw_rad'}:fail('mount','expected parent_frame, translation_m and yaw_rad')
            if mount['parent_frame']!='base_link' or mount['translation_m']!=[0,0] or mount['yaw_rad']!=0:
                fail('mount','current sensor components support only the confirmed center-aligned base_link mount')
            if s['type']=='radar':
                for key,expected in [('mount_m',mount['translation_m']),('yaw_rad',mount['yaw_rad']),('update_hz',s['update_hz'])]:
                    if key in p and p[key]!=expected:fail('parameters.'+key,'legacy parameter conflicts with the instance definition')
                    p[key]=copy.deepcopy(expected)
            if s['type']=='armor_detector':
                for key,expected in [('mount_m',mount['translation_m']),('yaw_rad',mount['yaw_rad'])]:
                    if key in p and p[key]!=expected:fail('parameters.'+key,'legacy parameter conflicts with the instance definition')
                    p[key]=copy.deepcopy(expected)
            stochastic=python_backend(s)
            default=None if not stochastic else {'id':p.get('random_stream',s['type']),'seed_mode':'legacy_seed' if s['type']=='radar' else 'named'}
            s.setdefault('random_stream',default)
            stream=s['random_stream']
            if not stochastic and stream is not None:fail('random_stream','ideal Rust sensor does not consume a random stream')
            if stochastic and stream is None:fail('random_stream','stochastic backend needs an explicit random stream')
            if (s['type']=='gps' or (s['type']=='wheel_encoder' and stochastic)) and isinstance(stream,dict) and stream.get('seed_mode')!='named':
                fail('random_stream.seed_mode','navigation measurement errors require an independent named stream')
            if s['type'] in ('armor_detector','intercepted_gps') and isinstance(stream,dict):
                if 'random_stream' in p and p['random_stream']!=stream['id']:fail('parameters.random_stream','random stream definitions disagree')
                p['random_stream']=stream['id']


def definitions(config):
    from .level_plugins import selected,SENSORS,LevelValidationError,error_path
    from tankbot_protocol.validation import Validator
    level=selected(config)
    if level:
        sensors=copy.deepcopy(level['sensors'])
    else:
        sensors=copy.deepcopy(config.get('sensor_instances'))
        if sensors is None:
            sensors=[{'type':kind,'topic':v[0],'schema':v[1],'frame_id':v[2],'update_hz':config['clock']['sensor_hz']} for kind,v in SENSORS.items() if v[3]]
    wrapper={'world':{'simulation':config['clock']},'robots':[{'id':'player','sensors':sensors}]}
    normalize_sensors(wrapper,'sensor_instances')
    validator=Validator(config,'sensor-resolution').schemas['level.schema.json']
    seen=set();topics=set();streams=set()
    for index,s in enumerate(sensors):
        path=f'sensor_instances[{index}]'
        # Validate the same schema for scene and legacy standalone instances.
        errors=list(validator.evolve(schema=validator.schema['$defs']['sensor']).iter_errors(s))
        if errors:raise LevelValidationError('resolved_scene',path+'.'+error_path(errors[0].absolute_path),errors[0].message)
        if s['id'] in seen or s['topic'] in topics:raise LevelValidationError('resolved_scene',path,'duplicate instance ID or output Topic')
        seen.add(s['id']);topics.add(s['topic'])
        if (s['topic'],s['schema'],s['frame_id'])!=SENSORS[s['type']][:3]:raise LevelValidationError('resolved_scene',path,'invalid registered output interface')
        if config['clock']['sensor_hz']%s['update_hz'] or (SENSORS[s['type']][3] and s['update_hz']!=config['clock']['sensor_hz']):raise LevelValidationError('resolved_scene',path+'.period_ticks','unsupported backend sample period')
        if s['random_stream']:
            stream=s['random_stream']['id']
            if stream in streams:raise LevelValidationError('resolved_scene',path+'.random_stream','duplicate random stream')
            streams.add(stream)
    result=[]
    for s in sensors:
        native=not python_backend(s)
        stream=s['random_stream'];mount=s['mount']
        publisher='authority' if native else 'sensor:'+s['type']
        result.append(SensorInstance(s['id'],s['robot_id'],s['type'],'rust' if native else 'python',
            Mount2D(mount['parent_frame'],*mount['translation_m'],mount['yaw_rad']),s['period_ticks'],
            RandomStream(**stream) if stream else None,s['topic'],s['schema'],s['frame_id'],publisher,
            json.dumps(s.get('parameters',{}),sort_keys=True,allow_nan=False)))
    return tuple(result)


class SensorScheduler:
    """Each run owns fresh adapters, RNGs and duplicate guards; no world references escape."""
    def __init__(self, instances, config):
        from .level_plugins import SENSORS
        from .campaign import RadarSimulator,active
        from .weapon_sensors import GpsInterceptSimulator,ArmorDetectionSimulator
        self.instances=tuple(instances);self._config=config
        self._backends={'radar':RadarSimulator(config) if active(config) else None,
                        'intercepted_gps':GpsInterceptSimulator(config),'armor_detector':ArmorDetectionSimulator(config)}
        from .navigation_sensors import EncoderMeasurement,GpsSimulator
        for instance in self.instances:
            if instance.type=='gps':self._backends[instance.type]=GpsSimulator(instance)
            elif instance.type=='wheel_encoder' and instance.backend=='python':
                self._backends[instance.type]=EncoderMeasurement(instance,config['clock']['physics_hz'])
        self._native={kind:entry[3] for kind,entry in SENSORS.items()}
        self.closed=False;self.reset()

    def backend(self,kind):return self._backends.get(kind)

    def reset(self):
        if self.closed:raise ValueError('SENSORS_CLOSED')
        self._last_tick=None
        for instance in self.instances:
            if instance.backend=='python':
                backend=self._backends[instance.type]
                seed=instance.random_stream.seed(self._config['runtime']['seed'])
                if hasattr(backend,'reset'):backend.reset(seed)
                else:
                    backend.last_tick=None
                    backend.random=random.Random(seed)

    def sample(self,private,tick):
        if self.closed:raise ValueError('SENSORS_CLOSED')
        if self._last_tick is not None and tick<self._last_tick:raise ValueError('SENSOR_TIME_REVERSED: reset before a new run')
        if self._last_tick==tick:return ()
        self._last_tick=tick
        if private['sensors'] is None:return ()
        result=[]
        for instance in self.instances:
            if tick%instance.period_ticks:continue
            if instance.backend=='rust':payload=private['sensors'].get(self._native[instance.type])
            else:payload=self._backends[instance.type].measure(private,tick)
            if payload is not None:result.append((instance,payload))
        return tuple(result)

    def close(self):
        self.closed=True;self._backends={};self._last_tick=None
