"""Authority-owned initial module grant; Manifest cannot widen this profile."""

def module_profile(config):
    level = config.get("campaign",{}).get("active_level")
    profile_name = config["campaign"]["levels"][level].get("robot_profile") if level else None
    if profile_name:
        import copy
        profile = config["robot_graph"]["profiles"][profile_name]
        mid = profile["manifest"]["modules"][0]["module_id"]
        contract = copy.deepcopy(profile["contracts"][mid])
        inputs = {c["to"].split(".")[1]:c["from"] for c in profile["manifest"]["connections"] if c["to"].startswith(mid+".")}
        outputs = {c["from"].split(".")[1]:c["to"] for c in profile["manifest"]["connections"] if c["from"].startswith(mid+".")}
        return contract,inputs,outputs
    period = config["clock"]["physics_hz"] // config["clock"]["algorithm_hz"]
    delay = config["runtime"]["commit_delay_ticks"]
    module_id = config["module"]["module_id"]
    if config.get("campaign", {}).get("active_level"):
        return ({"contract_version": "1.0", "module_id": module_id,
                 "entry_point": config["module"]["entry_point"],
                 "inputs": {"self_pose": {"schema": "pose2d@1", "required": True, "max_age_ticks": config["runtime"]["input_max_age_ticks"]},
                            "radar": {"schema": "radar@1", "required": False, "max_age_ticks": config["runtime"]["input_max_age_ticks"]}},
                 "outputs": {"target": {"schema": "target_estimate@1"}},
                 "execution": {"mode": "periodic", "period_ticks": period, "deadline_ticks": delay,
                               "budget_ms": config["runtime"]["batch_budget_ms"]},
                 "dependencies": [], "state_version": "1"},
                {"self_pose": "/robot/localization/pose", "radar": "/robot/sensors/radar"},
                {"target": f"/robot/estimates/{module_id}/target"})
    input_channels = {"wheels": "/robot/sensors/joint_states", "imu": "/robot/sensors/imu"}
    output_channels = {"pose": f"/robot/estimates/{module_id}/pose"}
    if config["weapons"]["enabled"]:
        input_channels.update(turret="/robot/turret/joint_states", weapon="/robot/weapons/cannon/state")
    contract = {"contract_version": "1.0", "module_id": module_id, "entry_point": config["module"]["entry_point"],
                     "inputs": {"wheels": {"schema": "joint_state@1", "required": True, "max_age_ticks": config["runtime"]["input_max_age_ticks"]},
                                "imu": {"schema": "imu@1", "required": False, "max_age_ticks": config["runtime"]["input_max_age_ticks"]}},
                     "outputs": {"pose": {"schema": "pose2d@1"}},
                     "execution": {"mode": "periodic", "period_ticks": period, "deadline_ticks": delay, "budget_ms": config["runtime"]["batch_budget_ms"]},
                     "dependencies": [], "state_version": "1"}
    if config["weapons"]["enabled"]:
        for port, schema in (("turret", "joint_state@1"), ("weapon", "weapon_state@1")):
            contract["inputs"][port] = {"schema":schema,"required":False,"max_age_ticks":config["runtime"]["input_max_age_ticks"]}
    for actuator, port, schema, channel in (("chassis","cmd_vel","twist@1","/robot/cmd_vel"),
            ("turret","turret_velocity","turret_velocity@1","/robot/turret/cmd_vel"),
            ("weapon","fire","fire_command@1","/robot/weapons/cannon/fire")):
        if config["control_sources"][actuator] == "robot" and (actuator == "chassis" or config["weapons"]["enabled"]):
            contract["outputs"][port] = {"schema":schema}
            output_channels[port] = channel
    return contract, input_channels, output_channels
