"""Resolve once, then instantiate fresh runs from immutable, validated scene definitions."""
from dataclasses import dataclass
import copy
import hashlib
import json
from .sensor_instances import SensorInstance,definitions
from .path_generation import ResolvedPath,prepare_path


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=False)


@dataclass(frozen=True)
class ResolvedWall:
    center: tuple[float,float]
    size: tuple[float,float]


@dataclass(frozen=True)
class ResolvedWorld:
    walls: tuple[ResolvedWall,...]
    physics_hz: int
    substeps: int
    solver_json: str


@dataclass(frozen=True)
class ResolvedChassis:
    id: str
    definition_json: str

    def to_dict(self):return json.loads(self.definition_json)


@dataclass(frozen=True)
class ResolvedRobot:
    id: str
    role: str
    chassis: ResolvedChassis
    initial_pose: tuple[float,float,float]
    initial_velocity: tuple[float,float,float]


@dataclass(frozen=True)
class ResolvedScene:
    definition_id: str
    level_id: str | None
    world: ResolvedWorld
    robots: tuple[ResolvedRobot,...]
    sensors: tuple[SensorInstance,...]
    _configuration_json: str
    path_reference: ResolvedPath | None = None

    def to_config(self):
        """Private compatibility DTO; never return a reference into the definition."""
        return json.loads(self._configuration_json)


def resolve_scene(config):
    if isinstance(config,ResolvedScene):return config
    from .chassis_profiles import apply_profiles
    from .maps import apply_override
    from .campaign import active,validate_profile
    from .wheel_geometry import validate_wheels
    from tankbot_protocol.validation import Validator
    c=apply_profiles(copy.deepcopy(config));apply_override(c)
    Validator(c,'scene-resolution').structure(c,'simulation-profile.schema.json')
    validate_profile(c);validate_wheels(c['wheels'])
    if c.get('wheel_drive') and (c['scene']['default_chassis']!='differential' or c['weapons']['enabled']):
        raise ValueError('wheel_voltage requires an unarmed differential chassis')
    hz=c['clock']['physics_hz']
    if hz%c['clock']['sensor_hz'] or hz%c['clock']['algorithm_hz'] or c['solver']['dt']!=1/(hz*c['clock']['substeps']):
        raise ValueError('Invalid resolved scene clock/solver')
    world=ResolvedWorld(tuple(ResolvedWall(tuple(w['center']),tuple(w['size'])) for w in c['scene']['walls']),hz,c['clock']['substeps'],canonical(c['solver']))
    def robot_model(name,target=None):
        # Record effective per-instance parameters, including trusted legacy DTO
        # overrides, rather than claiming the asset alone describes the runtime.
        model=copy.deepcopy(c.get('chassis_profiles',{}).get(name,{}))
        model['drive']=copy.deepcopy(c['chassis'][name])
        if target is None:
            model.update({key:copy.deepcopy(c[key]) for key in ('body','servo','motion_limits','controller')})
            model['wheels']=({'radius_m':c['wheels']['radius_m'],'track_m':c['wheels']['differential_track_m']} if name=='differential' else {'radius_m':c['wheels']['radius_m'],**copy.deepcopy(c['wheels']['omnidirectional'])})
        else:
            model['body']=copy.deepcopy(target.get('body',c['body']))
            for key in ('servo','motion_limits'):model[key]=copy.deepcopy(target.get(key,c[key]))
        return ResolvedChassis(name,canonical(model))
    robots=[ResolvedRobot('player','player',robot_model(c['scene']['default_chassis']),tuple(c['scene']['initial_pose']),tuple(c['scene']['initial_velocity']))]
    for target in c['weapons']['targets']:
        motion=target.get('motion',{})
        name=motion.get('chassis',c['scene']['default_chassis'])
        robots.append(ResolvedRobot(target['target_id'],'target',robot_model(name,target),tuple(target['pose']),tuple(motion.get('initial_velocity',[0.,0.,0.]))))
    instances=definitions(c)
    if any(s.robot_id not in {r.id for r in robots} for s in instances):raise ValueError('Unknown sensor owner')
    path_reference=prepare_path(c)
    encoded=canonical(c)
    return ResolvedScene(hashlib.sha256(encoded.encode()).hexdigest(),active(c),world,tuple(robots),instances,encoded,path_reference)


class SceneResolver:
    """Application-local cache. Asset edits take effect through a new resolver/load."""
    def __init__(self,scene):
        first=resolve_scene(scene)
        self._base=first.to_config()
        self._cache={first.level_id:first}

    def get(self,level_id):
        if level_id not in self._cache:
            from .campaign import configure
            self._cache[level_id]=resolve_scene(configure(self._base,level_id))
        return self._cache[level_id]
