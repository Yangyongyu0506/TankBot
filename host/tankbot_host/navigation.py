"""Public static calibration for wheel controllers; no world state or task callbacks."""
from tankbot import DifferentialDriveParameters
from dataclasses import asdict


def drive_parameters(config):
    motor=config["wheel_drive"]
    chassis=config["chassis"]["differential"]
    return asdict(DifferentialDriveParameters(
        wheel_radius_m=config["wheels"]["radius_m"],
        wheel_separation_m=config["wheels"]["differential_track_m"],
        mass_kg=config["body"]["mass_kg"],
        yaw_inertia_kg_m2=config["body"]["yaw_inertia_kg_m2"],
        drag_x_n_s_per_m=chassis["drag_x_n_s_per_m"],
        drag_yaw_nm_s=chassis["drag_yaw_nm_s"],
        **{key:motor[key] for key in ("resistance_ohm","torque_constant_nm_per_a","back_emf_v_s_per_rad","wheel_inertia_kg_m2","max_voltage_v")},
    ))
