"""Wheel-angle increments to body displacement, SI units, base_link x forward/y left."""
import math


def body_increment(names, deltas, wheels):
    q = dict(zip(names, deltas))
    r = wheels["radius_m"]
    if set(q) == {"left", "right"}:
        return r*(q["left"]+q["right"])/2, 0.0, r*(q["right"]-q["left"])/wheels["differential_track_m"]
    fl, fr, rl, rr = (q[k] for k in ("front_left", "front_right", "rear_left", "rear_right"))
    beta = math.radians(wheels["roller_angle_deg"])
    lateral = math.cos(beta)/math.sin(beta)
    k = wheels["mecanum_half_length_m"]*lateral + wheels["mecanum_half_width_m"]
    return r*(fl+fr+rl+rr)/4, r*(-fl+fr+rl-rr)/(4*lateral), r*(-fl+fr-rl+rr)/(4*k)
