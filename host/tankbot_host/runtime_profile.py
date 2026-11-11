"""Course-specific public initialization data, separate from scheduling and world ownership."""
import copy


def configure_course_runtime(authority,init,workspace):
    config=authority.config
    if not config.get("campaign",{}).get("active_level"):return
    from .chassis_profiles import target_geometry
    geometry=target_geometry(config)
    from .workspace import starter, read_sources
    init["sources"] = starter(config)
    if workspace is not None:
        init["sources"].update(read_sources(workspace, config["workspace"]))
    init["config"]["lesson"] = {"level_id": config["campaign"]["active_level"],
                                  "transform_tolerance": config["validation"]["numeric_tolerance"],
                                  "processing":authority.campaign.definition["runtime"]["processing"]}
    if config.get("wheel_drive"):
        from .navigation import drive_parameters
        init["config"]["drive_parameters"]=drive_parameters(config)
    if any(sensor.type=="gps" for sensor in authority.scene.sensors):
        from .navigation import localization_parameters
        init["config"]["localization_parameters"]=localization_parameters(config)
    if authority.campaign.definition["rules"].get("waypoint_route"):
        route = authority.campaign.navigation.spec
        contract = next(c for c in authority.campaign.definition["runtime"]["contracts"].values()
                        if c["entry_point"] == "navigation.waypoint_module:WaypointNavigationModule")
        init["config"]["navigation_parameters"] = {
            "position_tolerance_m": route["position_tolerance_m"],
            "control_limits": copy.deepcopy(route["control_limits"]),
            "pose_max_age_ticks": contract["inputs"]["pose"]["max_age_ticks"],
        }
    if authority.campaign.definition["rules"].get("path_tracking"):
        route=authority.campaign.navigation
        grants=authority.campaign.definition["permissions"]["data_access"]
        if "path_reference" not in grants.get("task_inputs",[]):
            raise ValueError("UNAUTHORIZED_PATH_REFERENCE")
        contract=next(c for c in authority.campaign.definition["runtime"]["contracts"].values()
                      if c["entry_point"]=="navigation.path_module:PathTrackingModule")
        reference=route.reference
        init["config"]["path_tracking_parameters"]={
            "reference":{key:copy.deepcopy(reference[key]) for key in ("path_id","points_m","frame_id","seed","parameters","input_sha256")},
            "control_limits":copy.deepcopy(route.spec["control_limits"]),
            "reference_speed_mps":route.spec["reference_speed_mps"],
            "position_tolerance_m":route.spec["position_tolerance_m"],
            "pose_max_age_ticks":contract["inputs"]["pose"]["max_age_ticks"],
        }
    if authority.campaign.definition["rules"].get("global_planning"):
        route=authority.campaign.navigation
        grants=authority.campaign.definition["permissions"]["data_access"]
        if not {"occupancy_grid", "planning_goal"} <= set(grants.get("task_inputs", [])):
            raise ValueError("UNAUTHORIZED_PLANNING_INPUT")
        contract=next(c for c in authority.campaign.definition["runtime"]["contracts"].values()
                      if c["entry_point"]=="navigation.path_module:PathTrackingModule")
        init["preparation"]=copy.deepcopy(authority.campaign.definition["runtime"]["preparation"])
        init["preparation_limits"]={"max_path_points":route.spec["max_path_points"]}
        init["config"]["path_tracking_parameters"]={
            "reference":None,
            "control_limits":copy.deepcopy(route.spec["control_limits"]),
            "reference_speed_mps":route.spec["reference_speed_mps"],
            "position_tolerance_m":route.spec["position_tolerance_m"],
            "pose_max_age_ticks":contract["inputs"]["pose"]["max_age_ticks"],
        }
    if authority.graph_profile() and authority.radar.noise is not None:
        noise = authority.radar.noise
        init["config"]["observations"] = {"radar_covariance":[[noise["range_stddev_m"]**2,0],[0,noise["bearing_stddev_rad"]**2]]}
    if authority.intercepted_gps.sensor:
        variance = authority.intercepted_gps.sensor["parameters"]["noise"]["position_stddev_m"]**2
        init["config"]["observations"].update(gps_covariance=[[variance,0],[0,variance]],gps_mount=geometry["gps_mount_m"])
    if authority.armor_detector.sensor:
        noise=authority.armor_detector.sensor["parameters"]["noise"]
        init["config"]["observations"]={"armor_covariance":[[noise["range_stddev_m"]**2,0],[0,noise["bearing_stddev_rad"]**2]],"armor_mounts":geometry["armor_mounts"]}
    if authority.graph_profile():
        import math
        init["config"]["lesson"]["tick_duration_s"] = 1/authority.hz
        init["config"]["lesson"]["estimate_history_ticks"] = config["runtime"]["estimate_history_ticks"]
        armor = authority.campaign.definition.get("armor_mode",False)
        if config["weapons"]["enabled"]:
            init["config"]["actuators"] = {"projectile_speed_mps":config["weapons"]["projectile"]["relative_speed_mps"],
                "max_acceleration_radps2":config["weapons"]["turret"]["acceleration_control"]["max_relative_acceleration_radps2"],
                "armor_mounts":geometry["armor_mounts"] if armor else [],
                "enemy_drive_model":authority.campaign.definition["target"]["motion"]["chassis"],
                "enemy_forward_only":authority.campaign.definition["target"]["motion"]["forward_speed_mps"] > 0}
