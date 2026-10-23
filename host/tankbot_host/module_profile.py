"""Authority-owned initial module grant; Manifest cannot widen this profile."""

def module_profile(config):
    period = config["clock"]["physics_hz"] // config["clock"]["algorithm_hz"]
    delay = config["runtime"]["commit_delay_ticks"]
    module_id = config["module"]["module_id"]
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
