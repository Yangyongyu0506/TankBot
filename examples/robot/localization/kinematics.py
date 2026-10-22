"""Wheel-angle increments to body displacement, SI units, base_link x forward/y left.

radial_omni@1 uses inward radial positive axles and CCW tangential rolling.
This is a repository reference algorithm; runtime never overwrites player files.
"""
import math


def body_increment(names, deltas, wheels):
    if len(names)!=len(deltas) or len(set(names))!=len(names):
        raise ValueError("Wheel samples require matching unique names")
    q = dict(zip(names, deltas))
    r = wheels["radius_m"]
    if set(q) == {"left", "right"}:
        return r*(q["left"]+q["right"])/2, 0.0, r*(q["right"]-q["left"])/wheels["differential_track_m"]
    geometry=wheels["omnidirectional"]
    if geometry["geometry_version"]!="radial_omni@1":
        raise ValueError("Unsupported wheel calibration version")
    mounts=geometry["wheels"]
    if set(q)!={m["name"] for m in mounts} or len(mounts)!=4:
        raise ValueError("Wheel sample does not match radial omni calibration")
    dx=dy=da=0.0
    for mount in mounts:
        angle=math.radians(mount["azimuth_deg"])
        delta=q[mount["name"]]
        dx-=r*math.sin(angle)*delta/2
        dy+=r*math.cos(angle)*delta/2
        da+=r*delta/(4*geometry["center_radius_m"])
    return dx,dy,da
