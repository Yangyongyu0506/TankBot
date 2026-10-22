"""Public wheel calibration validation. No world or dynamic robot state."""
import math


def validate_wheels(wheels):
    geometry=wheels['omnidirectional']
    if geometry['geometry_version']!='radial_omni@1' or any(not math.isfinite(v) or v<=0 for v in (wheels['radius_m'],wheels['differential_track_m'],geometry['center_radius_m'])):
        raise ValueError('Invalid radial omni calibration')
    mounts=geometry['wheels']
    if len(mounts)!=4 or len({m['name'] for m in mounts})!=4:
        raise ValueError('Four unique omni wheels are required')
    angles=sorted(m['azimuth_deg'] for m in mounts)
    if any(not math.isfinite(a) or not 0<=a<360 for a in angles):
        raise ValueError('Invalid omni wheel azimuth')
    if any(abs((angles[(i+1)%4]-a)%360-90)>math.ulp(360.0)*8 for i,a in enumerate(angles)):
        raise ValueError('Omni wheels must be 90 degrees apart')


def public_calibration(wheels):
    import copy
    return {'radius_m':wheels['radius_m'],**copy.deepcopy(wheels['omnidirectional'])}
