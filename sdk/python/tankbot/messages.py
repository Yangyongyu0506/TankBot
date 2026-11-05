"""One registry for SDK output types and runtime input decoding; schemas remain normative."""
from . import (PositionFix2D, ImuData, RadarData, ArmorDetections, Pose2D, TargetEstimate,
               TargetPoseEstimate, TargetPoints, GpsFixData, PolarTargetEstimate,
               TurretAcceleration, TurretVelocity, WaypointGoal, Twist, Vector3,
               JointState, WeaponState, WheelVoltage)

MESSAGE_TYPES = {
    'position_fix2d@1': (PositionFix2D, False), 'imu@1': (ImuData, False),
    'radar@1': (RadarData, False), 'armor_detections@1': (ArmorDetections, False),
    'pose2d@1': (Pose2D, True), 'target_estimate@1': (TargetEstimate, True),
    'target_pose_estimate@1': (TargetPoseEstimate, True), 'target_points@1': (TargetPoints, True),
    'gps_fix@1': (GpsFixData, False), 'target_polar_estimate@1': (PolarTargetEstimate, True),
    'turret_acceleration@1': (TurretAcceleration, True), 'turret_velocity@1': (TurretVelocity, True),
    'waypoint_goal@1': (WaypointGoal, False), 'twist@1': (Twist, True),
    'joint_state@1': (JointState, False), 'weapon_state@1': (WeaponState, False),
    'wheel_voltage@1': (WheelVoltage, True),
}
OUTPUT_SCHEMAS = {kind: schema for schema, (kind, publishable) in MESSAGE_TYPES.items() if publishable}


def decode_message(schema: str, payload: dict):
    kind = MESSAGE_TYPES[schema][0]
    if kind is Twist:return Twist(Vector3(**payload['linear']),Vector3(**payload['angular']))
    if kind is JointState:return JointState(**{key:tuple(value) for key,value in payload.items()})
    return kind(**payload)
