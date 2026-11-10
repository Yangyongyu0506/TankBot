"""Trusted configuration selection. Player messages and telemetry never select a profile."""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BACKENDS=('native','pyodide')


def milliseconds_ns(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError('RUNTIME_PROFILE_VALUE: positive finite milliseconds required')
    ticks=Decimal(str(value))*1_000_000
    if ticks!=ticks.to_integral_value():
        raise ValueError('RUNTIME_PROFILE_VALUE: deadline must be representable in integer nanoseconds')
    return int(ticks)


def load_execution_profiles(config):
    runtime=config['runtime']
    if 'profiles_file' in runtime:
        if 'profiles' in runtime or 'batch_budget_ms' in runtime:
            raise ValueError('RUNTIME_PROFILE_CONFLICT: profiles_file cannot coexist with profiles or batch_budget_ms')
        path=(ROOT/runtime['profiles_file']).resolve()
        if not path.is_relative_to(ROOT/'config') or path.suffix not in ('.yaml','.yml'):
            raise ValueError('RUNTIME_PROFILE_PATH: expected a trusted config YAML asset')
        from .configuration import load_yaml
        runtime['profiles']=load_yaml(path)
        runtime.pop('profiles_file')
    validate_execution_profiles(config)


def validate_execution_profiles(config):
    runtime=config['runtime']
    if ('profiles' in runtime)==('batch_budget_ms' in runtime):
        raise ValueError('RUNTIME_PROFILE_CONFLICT: use exactly one of profiles and legacy batch_budget_ms')
    if 'batch_budget_ms' in runtime:
        milliseconds_ns(runtime['batch_budget_ms'])
        return
    from tankbot_protocol.validation import Validator
    catalog=runtime['profiles']
    Validator(config,'execution-profiles').structure(catalog,'runtime-execution.schema.json')
    milliseconds_ns(catalog['module_declared_budget_cap_ms'])
    for backend in BACKENDS:
        identity=catalog['defaults'][backend]
        if identity not in catalog['profiles'] or catalog['profiles'][identity]['backend']!=backend:
            raise ValueError('RUNTIME_PROFILE_BACKEND: defaults.'+backend+' must name a matching profile')
    for profile in catalog['profiles'].values():milliseconds_ns(profile['batch_wall_deadline_ms'])


def admission_cap(config):
    validate_execution_profiles(config)
    runtime=config['runtime']
    return runtime['profiles']['module_declared_budget_cap_ms'] if 'profiles' in runtime else runtime['batch_budget_ms']


@dataclass(frozen=True)
class ExecutionProfile:
    profile_id: str
    profile_version: str
    backend: str
    module_declared_budget_cap_ms: float
    batch_wall_deadline_ms: float
    status: str
    source: str

    @property
    def wall_deadline_ns(self):return milliseconds_ns(self.batch_wall_deadline_ms)

    def public(self):
        from dataclasses import asdict
        value=asdict(self)
        value['sha256']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return value


def select_execution_profile(config,backend):
    if backend not in BACKENDS:raise ValueError('RUNTIME_PROFILE_BACKEND: '+str(backend))
    validate_execution_profiles(config)
    runtime=config['runtime']
    if 'batch_budget_ms' in runtime:
        budget=runtime['batch_budget_ms']
        return ExecutionProfile('legacy_'+backend+'_v1','1.0',backend,budget,budget,'legacy','batch_budget_ms')
    catalog=runtime['profiles'];identity=catalog['defaults'][backend];profile=catalog['profiles'][identity]
    return ExecutionProfile(identity,profile['profile_version'],backend,catalog['module_declared_budget_cap_ms'],
                            profile['batch_wall_deadline_ms'],profile['status'],'profiles')
