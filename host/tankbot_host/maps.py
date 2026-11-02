"""Trusted map assets, launch overrides and permission-filtered preview data."""
import copy
import math
from pathlib import Path
from .level_plugins import ROOT, resolve_map, LevelValidationError


def asset_path(name):
    if not isinstance(name,str) or not name.strip():
        raise ValueError('MAP_NOT_FOUND: 请指定 assets/maps 中的地图名称。')
    relative=Path(name)
    if not relative.parts or relative.is_absolute() or '..' in relative.parts:
        raise ValueError('INVALID_MAP_PATH: 地图必须位于 assets/maps/。')
    if relative.parts[0]=='assets':relative=Path(*relative.parts[1:])
    if not relative.parts or relative.parts[0]!='maps':relative=Path('maps')/relative
    if not relative.suffix:relative=relative.with_suffix('.yaml')
    root=(ROOT/'assets/maps').resolve();path=(ROOT/'assets'/relative).resolve()
    if relative.suffix not in ('.yaml','.yml') or not path.is_relative_to(root) or not path.is_file():
        raise ValueError('MAP_NOT_FOUND: '+name+'；运行 --list-maps 查看可用地图。')
    return path.relative_to(ROOT/'assets').as_posix()


def discover_maps(config):
    root=ROOT/'assets/maps'
    paths=sorted([*root.rglob('*.yaml'),*root.rglob('*.yml')])
    if len(paths)>config['level_plugins']['limits']['max_files']:
        raise LevelValidationError(root,'$','too many map assets')
    return [{'path':asset_path(path.relative_to(ROOT/'assets').as_posix()),
             'walls':resolve_map({'source':'asset','path':path.relative_to(ROOT/'assets').as_posix()},path,config)} for path in paths]


def set_override(config,name):
    candidate=copy.deepcopy(config)
    path=asset_path(name)
    candidate['map_override']={'path':path,'walls':resolve_map({'source':'asset','path':path},'--map',config)}
    return apply_override(candidate)


def _overlaps(pose,body,wall,tolerance):
    x,y,yaw=pose;c,s=math.cos(yaw),math.sin(yaw)
    axes=((c,s),(-s,c),(1.,0.),(0.,1.))
    dx,dy=wall['center'][0]-x,wall['center'][1]-y
    hx,hy=body['length_m']/2,body['width_m']/2
    wx,wy=wall['size'][0]/2,wall['size'][1]/2
    for ax,ay in axes:
        radius=hx*abs(ax*c+ay*s)+hy*abs(-ax*s+ay*c)+wx*abs(ax)+wy*abs(ay)
        if abs(dx*ax+dy*ay)>=radius-tolerance:return False
    return True


def apply_override(config):
    override=config.get('map_override')
    if not override:return config
    from .chassis_profiles import body_for
    walls=override['walls'];tolerance=config['validation']['numeric_tolerance']
    bodies=[('player',config['scene']['initial_pose'],body_for(config,config['scene']['default_chassis']))]
    for target in config['weapons']['targets']:
        chassis=target.get('motion',{}).get('chassis',config['scene']['default_chassis'])
        bodies.append((target['target_id'],target['pose'],target.get('body',body_for(config,chassis))))
    for name,pose,body in bodies:
        for index,wall in enumerate(walls):
            if _overlaps(pose,body,wall,tolerance):
                raise ValueError(f'MAP_SPAWN_BLOCKED: {override["path"]} 的 walls[{index}] 与 {name} 初始车体包围矩形重叠；请选择其他地图或调整场景初态，不会自动移动机器人。')
    config['scene']['walls']=copy.deepcopy(walls)
    return config


def preview_entry(identifier,walls):
    return {'id':identifier,'name':Path(identifier).stem.replace('_',' '),'walls':copy.deepcopy(walls)}


def preview_catalog(config,developer=False):
    # Ordinary viewers cannot turn the map library into a truth-map bypass.
    policy=config['view_policy']
    visible=developer or bool(config['scene']['public_map'] and policy['public_map'])
    level=config.get('campaign',{}).get('levels',{}).get(config.get('campaign',{}).get('active_level'))
    if level and 'map' not in level['permissions']['visualization']['allowed_layers'] and not developer:visible=False
    override=config.get('map_override')
    current=preview_entry('current',config['scene']['walls']) if visible else None
    if current:current['name']='当前场景'+(' · '+Path(override['path']).stem if override else '')
    entries=discover_maps(config) if developer else []
    return {'current':current,'maps':[preview_entry(e['path'],e['walls']) for e in entries],
            'overridden':bool(override),'override_path':override['path'] if override and visible else None,
            'developer':developer}
