"""Pure-data level discovery, validation and compilation into the existing Host/Core DTOs."""
import copy
import json
from pathlib import Path

from tankbot_protocol.validation import Validator
from .configuration import load_yaml

ROOT = Path(__file__).resolve().parents[2]
SENSORS = {
    "wheel_encoder":("/robot/sensors/joint_states","joint_state@1","base_link","joint_state"),
    "imu":("/robot/sensors/imu","imu@1","base_link","imu"),
    "turret_joint":("/robot/turret/joint_states","joint_state@1","base_link","turret"),
    "weapon_state":("/robot/weapons/cannon/state","weapon_state@1","base_link","weapon"),
    "radar":("/robot/sensors/radar","radar@1","radar_link",None),
}
ACTUATORS = {"/robot/cmd_vel":("twist@1","chassis","control.robot.drive"),
              "/robot/turret/cmd_vel":("turret_velocity@1","turret","control.robot.turret_velocity"),
              "/robot/turret/cmd_accel":("turret_acceleration@1","turret","control.robot.turret_acceleration"),
              "/robot/weapons/cannon/fire":("fire_command@1","weapon","control.robot.fire")}


class LevelValidationError(ValueError):
    def __init__(self, filename, path, reason):
        self.filename, self.path, self.reason = str(filename), path, reason
        super().__init__(f"LevelValidationError\nFile: {filename}\nPath: {path}\nReason: {reason}")


def error_path(parts):
    result = ""
    for part in parts:
        result += f"[{part}]" if isinstance(part,int) else ("." if result else "")+str(part)
    return result or "$"


def read_definition(path, limits):
    import yaml
    try:
        with path.open("rb") as stream:
            raw = stream.read(limits["max_file_bytes"]+1)
        if len(raw) > limits["max_file_bytes"]:
            raise ValueError("file exceeds max_file_bytes")
        depth = nodes = 0
        for event in yaml.parse(raw):
            nodes += 1
            if isinstance(event,yaml.events.AliasEvent):
                raise ValueError("YAML aliases are not allowed")
            if isinstance(event,(yaml.events.MappingStartEvent,yaml.events.SequenceStartEvent)):
                depth += 1
            if isinstance(event,(yaml.events.MappingEndEvent,yaml.events.SequenceEndEvent)):
                depth -= 1
            if depth > limits["max_depth"] or nodes > limits["max_nodes"]:
                raise ValueError("YAML exceeds nesting/node limits")
        return load_yaml(path,content=raw)
    except (ValueError,yaml.YAMLError,UnicodeError,RecursionError) as exc:
        raise LevelValidationError(path,"$",str(exc)) from exc


def selected(config):
    campaign = config.get("campaign",{})
    return campaign.get("levels",{}).get(campaign.get("active_level"))


def runtime_profile(config):
    level = selected(config)
    return level.get("runtime") if level else None


def _validate(value, filename, config, validator):
    errors = list(validator.schemas["level.schema.json"].iter_errors(value))
    if errors:
        # Composite-rule failures contain branch diagnostics; prefer the actual field.
        def leaves(error):
            return [item for child in error.context for item in leaves(child)] if error.context else [error]
        detailed = [leaf for error in errors for leaf in leaves(error)]
        error = max(detailed,key=lambda e:(len(e.absolute_path),e.validator not in ("const","enum")))
        raise LevelValidationError(filename,error_path(error.absolute_path),error.message)
    def fail(path,reason):raise LevelValidationError(filename,path,reason)
    limits = config["level_plugins"]["limits"]
    robots = value["robots"]
    if len(robots)>limits["max_robots"]:fail("robots","component count exceeds max_robots")
    ids = [r["id"] for r in robots]
    if len(set(ids))!=len(ids):fail("robots","duplicate robot ID")
    players = [r for r in robots if r["role"]=="player"]
    targets = [r for r in robots if r["role"]=="target"]
    if len(players)!=1 or len(targets)!=1:fail("robots","current components require one player and one objective target")
    player,target = players[0],targets[0]
    if value["objectives"]["target"]!=target["id"]:fail("objectives.target","unknown objective target robot")
    if target["type"]=="patrol_tank" and not target["parameters"].get("motion"):fail("robots","patrol_tank requires motion parameters")
    if target["type"]=="static_tank_target" and target["parameters"].get("motion"):fail("robots","static target cannot declare a patrol")
    clock = value["world"]["simulation"]
    if clock["physics_hz"]%clock["sensor_hz"] or clock["physics_hz"]%clock["algorithm_hz"]:fail("world.simulation","rates must divide physics_hz")
    if clock["physics_hz"]%config["view"]["snapshot_hz"]:fail("world.simulation.physics_hz","view frequency must divide physics frequency")
    if clock["physics_hz"]//clock["algorithm_hz"]<config["runtime"]["commit_delay_ticks"]:fail("world.simulation.algorithm_hz","algorithm interval is shorter than the commit delay")
    sensor_topics = {"/robot/localization/pose":"pose2d@1"}
    sensor_ids = []
    if len(player["sensors"])>limits["max_sensors"]:fail("robots[0].sensors","component count exceeds max_sensors")
    for index,sensor in enumerate(player["sensors"]):
        path = f"robots[{robots.index(player)}].sensors[{index}]"
        topic,schema,frame,_ = SENSORS[sensor["type"]]
        if (sensor["topic"],sensor["schema"],sensor["frame_id"])!=(topic,schema,frame):fail(path,"component uses a different canonical Topic/schema/frame")
        sensor_ids.append(sensor["type"])
        sensor_topics[topic]=schema
        if clock["physics_hz"]%sensor["update_hz"] or clock["sensor_hz"]%sensor["update_hz"]:fail(path+".update_hz","rate must divide physics and sensor rates")
        if sensor["type"]!="radar" and sensor["update_hz"]!=clock["sensor_hz"]:fail(path+".update_hz","this component samples at the base sensor rate")
        if sensor["type"]=="radar":
            p = sensor["parameters"]
            if p["update_hz"]!=sensor["update_hz"]:fail(path+".parameters.update_hz","sensor rates disagree")
            if p["mount_m"]!=[0,0] or p["yaw_rad"]!=0:fail(path+".parameters.mount_m","current Radar supports only center-aligned mounting")
    if len(sensor_ids)!=len(set(sensor_ids)):fail("robots[0].sensors","duplicate sensor/Topic")
    grants = value["permissions"]["data_access"]
    for channel,schema in grants["inputs"].items():
        if sensor_topics.get(channel)!=schema:fail("permissions.data_access.inputs."+channel,"unknown or undeclared input Topic/type")
    for channel,schema in grants["actuators"].items():
        component=ACTUATORS.get(channel)
        if not component or component[0]!=schema:fail("permissions.data_access.actuators."+channel,"unknown actuator Topic/type")
        if player["control_sources"][component[1]]!="robot":fail("permissions.data_access.actuators."+channel,"actuator does not grant robot control")
    schemas = config["robot_graph"]["schemas"]
    if any(s not in schemas for s in grants["outputs"]):fail("permissions.data_access.outputs","unknown output schema")
    layers = value["permissions"]["visualization"]["allowed_layers"]
    from .application import LAYERS
    if not set(layers)<=set(LAYERS):fail("permissions.visualization.allowed_layers","unknown visualization component")
    vis = value["visualization"]
    for name in ("initial_enabled","user_toggleable"):
        if not set(vis[name])<=set(layers):fail("visualization."+name,"display state exceeds visualization permission")
    if set(vis["sources"])!=set(layers):fail("visualization.sources","each allowed layer needs exactly one source")
    for layer,source in vis["sources"].items():
        expected="authorized_truth" if layer in ("truth_targets","projectiles") else "map" if layer=="map" else "selected_pose" if layer in ("robot","trail","frames") else "player_estimate" if layer=="target_estimates" else "local_observation"
        if source!=expected:fail("visualization.sources."+layer,"source is not supported by this visualization component")
    policy=value["permissions"]["visualization"]["view_policy"]
    if "truth_targets" in layers and not policy["true_enemy_objects"]:fail("permissions.visualization.allowed_layers","target truth is not authorized")
    if "projectiles" in layers and not policy["world_effects"]:fail("permissions.visualization.allowed_layers","projectile truth is not authorized")
    if set(layers)&{"truth_robot","velocities","colliders"}:fail("permissions.visualization.allowed_layers","these components require the separate developer grant")
    if any(ch not in sensor_topics for ch in policy["local_observation_channels"]):fail("permissions.visualization.view_policy.local_observation_channels","undeclared sensor Topic")
    runtime = value["communication"]["runtime"]
    from .level_templates import COMPONENTS
    from .workspace import validate_files
    import ast
    files={}
    for component in value["scaffolding"]["components"]:files.update(COMPONENTS[component])
    entry_points=set()
    for path,source in files.items():
        if path.endswith(".py"):
            for node in ast.walk(ast.parse(source)):
                if isinstance(node,ast.ClassDef) and any(isinstance(base,ast.Name) and base.id=="Module" for base in node.bases):
                    entry_points.add(path[:-3].replace("/",".")+":"+node.name)
    for path,notes in value["scaffolding"]["documentation"].items():
        if path not in files:fail("scaffolding.documentation."+path,"documentation references an undeclared template file")
        functions={n.name for n in ast.walk(ast.parse(files[path])) if isinstance(n,ast.FunctionDef)}
        if any(note["function"] not in functions for note in notes):fail("scaffolding.documentation."+path,"unknown template function")
    if value["tutorial"]["lesson"]["ui"]["default_file"] not in files:fail("tutorial.lesson.ui.default_file","unknown editor file")
    for index,fn in enumerate(value["tutorial"]["lesson"]["functions"]):
        if fn["path"] not in files or not any(isinstance(n,ast.FunctionDef) and n.name==fn["name"] for n in ast.walk(ast.parse(files[fn["path"]]))):fail(f"tutorial.lesson.functions[{index}]","unknown scaffold function")
    from .level_templates import sources
    from string import Formatter
    fields={"movement_m","turn_rad","required_hits","required_estimates","time_limit_s","max_hp","damage_per_hit","algorithm_hz","radar_hz","range_stddev_m","bearing_stddev_rad","drop_probability"}
    for key in ("completion","execution"):
        try:
            if any(field and field not in fields for _,field,_,_ in Formatter().parse(value["tutorial"]["lesson"][key])):raise ValueError("unknown public placeholder")
        except ValueError as exc:fail("tutorial.lesson."+key,str(exc))
    try:
        generated=sources(value)
        generated["tankbot.json"]=json.dumps(runtime["manifest"],indent=2)+"\n"
        for mid,contract in runtime["contracts"].items():generated[f"contracts/{mid}.json"]=json.dumps(contract,indent=2)+"\n"
        validate_files(generated,config["workspace"])
        for path,source in generated.items():
            if path.endswith(".py"):ast.parse(source,filename=path)
    except (ValueError,SyntaxError) as exc:fail("scaffolding",str(exc))
    player_files={"perception/transforms.py","perception/tracker.py","perception/pose_tracker.py","weapons/auto_aim.py","weapons/armor_aim.py"}
    registered={p for component in COMPONENTS.values() for p in component}
    managed={p for p in registered|set(generated) if p not in player_files and not p.endswith("__init__.py")}
    if not set(runtime["managed_files"])<=managed:fail("communication.runtime.managed_files","managed files must exclude player algorithms and custom files")
    modules=runtime["manifest"]["modules"]
    if len(modules)>config["robot_graph"]["max_modules"]:fail("communication.runtime.manifest.modules","too many modules")
    module_ids=[m["module_id"] for m in modules]
    for index,module in enumerate(modules):
        if module["contract"]!=f"contracts/{module['module_id']}.json":fail(f"communication.runtime.manifest.modules[{index}].contract","contract path must match the generated module contract")
    if len(module_ids)!=len(set(module_ids)):fail("communication.runtime.manifest.modules","duplicate module ID")
    if set(module_ids)!=set(runtime["contracts"]):fail("communication.runtime.contracts","contracts must match manifest modules")
    from .robot_graph import setup_order
    try:setup_order({mid:{"contract":c} for mid,c in runtime["contracts"].items()})
    except ValueError as exc:fail("communication.runtime.contracts",str(exc))
    if runtime["mode"]=="single" and len(modules)!=1:fail("communication.runtime.mode","single mode needs exactly one module")
    if runtime["target_source"] not in module_ids:fail("communication.runtime.target_source","unknown target publisher")
    for mid,contract in runtime["contracts"].items():
        path="communication.runtime.contracts."+mid
        if contract["entry_point"] not in entry_points:fail(path+".entry_point","entry point is not a registered scaffold component")
        if contract["module_id"]!=mid:fail(path+".module_id","contract module ID mismatch")
        execution=contract["execution"]
        interval=execution["period_ticks"] if execution["mode"]=="periodic" else execution["min_interval_ticks"]
        if execution["deadline_ticks"]!=config["runtime"]["commit_delay_ticks"] or interval<execution["deadline_ticks"]:fail(path+".execution","unsupported schedule/deadline")
        if runtime["mode"]=="single" and (execution["mode"]!="periodic" or interval!=clock["physics_hz"]//clock["algorithm_hz"]):fail(path+".execution","single-module schedule must match the declared algorithm frequency")
    if runtime["manifest"]["entry_point"] not in {c["entry_point"] for c in runtime["contracts"].values()}:fail("communication.runtime.manifest.entry_point","entry point is not a declared module")
    if sum(c["execution"]["budget_ms"] for c in runtime["contracts"].values())>config["runtime"]["batch_budget_ms"]:fail("communication.runtime.contracts","robot batch budget exceeded")
    writers={};bound=set()
    subscriptions=[]
    if len(runtime["manifest"]["connections"])>config["robot_graph"]["max_connections"]:fail("communication.runtime.manifest.connections","too many connections")
    for index,connection in enumerate(runtime["manifest"]["connections"]):
        source,destination=connection["from"],connection["to"]
        path=f"communication.runtime.manifest.connections[{index}]"
        if source.startswith("/"):
            subscriptions.append((source,destination,path));continue
        if not destination.startswith("/"):fail(path,"connections need explicit Topics")
        mid,port=source.split(".")
        contract=runtime["contracts"].get(mid,{})
        if port not in contract.get("outputs",{}):fail(path,"unknown output port")
        schema=contract["outputs"][port]["schema"]
        if (mid,port,"output") in bound:fail(path,"multiple output bindings")
        bound.add((mid,port,"output"))
        if destination in writers:fail(path,"multiple Topic publishers")
        if destination in ACTUATORS:
            if grants["actuators"].get(destination)!=schema:fail(path,"actuator publication denied")
        elif destination==f"/robot/modules/{mid}/{port}":
            if schema not in config["robot_graph"]["internal_schemas"]:fail(path,"unsupported internal type")
        elif not (destination.startswith(f"/robot/estimates/{mid}/") and schema in grants["outputs"]):fail(path,"output publication denied")
        writers[destination]=schema
    for source,destination,path in subscriptions:
        if destination.startswith("/") or "." not in destination:fail(path,"invalid subscription port")
        mid,port=destination.split(".")
        binding=runtime["contracts"].get(mid,{}).get("inputs",{}).get(port)
        if not binding:fail(path,"unknown input port")
        if (mid,port,"input") in bound:fail(path,"multiple input bindings")
        bound.add((mid,port,"input"))
        schema=writers.get(source,grants["inputs"].get(source))
        if schema is None:
            if binding["required"] or sensor_topics.get(source,dict((v[0],v[1]) for v in SENSORS.values()).get(source))!=binding["schema"]:fail(path,"input subscription denied")
        elif schema!=binding["schema"]:fail(path,"Topic type mismatch")
    for mid,contract in runtime["contracts"].items():
        for direction in ("input","output"):
            for port in contract[direction+"s"]:
                if (mid,port,direction) not in bound:fail("communication.runtime.contracts."+mid+"."+direction+"s."+port,"unbound port")
    metric_ids=[m["id"] for m in value["evaluation"]["metrics"]]
    if len(metric_ids)!=len(set(metric_ids)):fail("evaluation.metrics","duplicate metric ID")
    expected_metrics={"position_rmse":"rmse_m","yaw_rmse":"yaw_rmse_rad"}
    if any(expected_metrics[m["type"]]!=m["id"] for m in value["evaluation"]["metrics"]):fail("evaluation.metrics","metric ID must match its existing report field")
    feedback=value["evaluation"].get("live_feedback")
    if feedback:
        metric=feedback["metric"]
        if metric not in metric_ids:fail("evaluation.live_feedback.metric","live metric must be declared in evaluation.metrics")
        if metric not in value["permissions"]["visualization"].get("allowed_metrics",[]):fail("evaluation.live_feedback.metric","live metric visualization is not authorized")
    reasons=[o["reason"] for o in value["objectives"]["outcomes"]]
    if len(reasons)!=len(set(reasons)):fail("objectives.outcomes","duplicate terminal reason")


def _map(definition, source, config):
    spec=definition["world"]["map"]
    if spec["source"]=="inline":
        if "walls" not in spec or "path" in spec:raise LevelValidationError(source,"world.map","inline map needs walls only")
        return copy.deepcopy(spec["walls"])
    if "path" not in spec or "walls" in spec:raise LevelValidationError(source,"world.map","asset map needs path only")
    assets=(ROOT/"assets").resolve()
    path=(assets/spec["path"]).resolve()
    if not path.is_relative_to(assets) or not path.is_file():raise LevelValidationError(source,"world.map.path","map must be an existing asset inside assets/")
    result=read_definition(path,config["level_plugins"]["limits"])
    if not isinstance(result,dict) or set(result)!={"walls"}:raise LevelValidationError(source,"world.map.path","map asset uses the existing {walls: [...]} format")
    # Validate wall geometry with the existing simulation-profile definition.
    v=Validator(config,"map").schemas["simulation-profile.schema.json"]
    from jsonschema import Draft202012Validator
    from referencing import Registry,Resource
    registry=Registry().with_resource(v.schema["$id"],Resource.from_contents(v.schema))
    schema={"type":"array","items":{"$ref":v.schema["$id"]+"#/properties/scene/properties/walls/items"}}
    errors=list(Draft202012Validator(schema,registry=registry).iter_errors(result["walls"]))
    if errors:raise LevelValidationError(source,"world.map.path",errors[0].message)
    return result["walls"]


def _compile(value, walls):
    p=next(r for r in value["robots"] if r["role"]=="player")
    target=next(r for r in value["robots"] if r["role"]=="target")
    d=copy.deepcopy(value)
    meta=d["metadata"];runtime=d["communication"]["runtime"]
    radar=next((s["parameters"] for s in p["sensors"] if s["type"]=="radar"),None)
    policy=d["permissions"]["visualization"]["view_policy"]
    grants=d["permissions"]["data_access"]
    # Layer permissions cap the Authority projection as well as ordinary UI toggles.
    # They never widen or restrict the independent program input grants.
    layers=set(d["permissions"]["visualization"]["allowed_layers"])
    policy["true_enemy_objects"] &= "truth_targets" in layers
    policy["world_effects"] &= "projectiles" in layers
    policy["target_estimates_allowed"] &= "target_estimates" in layers
    if not layers & {"robot","trail","frames"}:
        policy["system_pose_allowed"]=policy["player_pose_allowed"]=False
    if "map" not in layers:policy["public_map"]=None
    observation_layers={"/robot/sensors/joint_states":"encoders","/robot/sensors/imu":"imu",
                        "/robot/turret/joint_states":"turret","/robot/weapons/cannon/state":"turret",
                        "/robot/sensors/radar":"radar"}
    policy["local_observation_channels"]=[channel for channel in policy["local_observation_channels"] if observation_layers.get(channel) in layers]
    runtime["grants"]=copy.deepcopy(grants)
    caps=[]
    if "/robot/localization/pose" in grants["inputs"]:caps.append("system.pose.read")
    if set(grants["outputs"])&{"target_estimate@1","target_pose_estimate@1"}:caps.append("estimate.target.publish")
    caps += [cap for actuator,cap in (("chassis","control.manual.drive"),("turret","control.manual.turret"),("weapon","control.manual.fire")) if p["control_sources"][actuator]=="keyboard"]
    if radar and radar["noise"] is not None:caps.append("sensor.radar.read")
    if policy["true_enemy_objects"]:caps.append("view.enemy.truth")
    if policy["world_effects"]:caps.append("view.projectiles.truth")
    if target["parameters"].get("health"):caps.append("view.enemy.health")
    if p["health"]:caps.append("view.player.health")
    caps += [ACTUATORS[channel][2] for channel in grants["actuators"]]
    if policy.get("robot_topics_allowed"):caps.append("view.robot_topics")
    if runtime["mode"]=="graph":caps.append("module.graph.manage")
    if "target_pose_estimate@1" in grants["outputs"]:caps.append("estimate.target_pose.publish")
    definition={"title":meta["name"],"problem":d["tutorial"]["problem"],"hints":d["tutorial"]["hints"],
        "chapter_id":meta["chapter"]["chapter_id"],"capabilities":caps,"target":{"target_id":target["id"],"pose":target["initial_pose"],**target["parameters"]},
        "objective":{**d["objectives"]["parameters"],"kind":"checklist" if d["objectives"]["success"]["type"]=="all" else "destroy_target"},
        "time_limit_s":d["objectives"]["time_limit_s"],"timer_start":d["objectives"]["timer_start"],
        "player_health":"same_as_target" if p["health"]==target["parameters"].get("health") and p["health"] else None,
        "control_sources":p["control_sources"],"robot_profile":runtime["profile_id"],"armor_mode":bool(target["parameters"].get("armor")),
        "radar_profile":("noisy" if any(radar["noise"].values()) else "ideal") if radar else None,
        "scene":{**({"default_chassis":p["model"]} if p["model"]!="scene_selected" else {}),"initial_pose":p["initial_pose"],"initial_velocity":p["initial_velocity"],"player_health":p["health"],"walls":walls,
                 "public_initial_pose":d["permissions"]["public_initial_pose"],"public_map":d["permissions"]["public_map"]},
        "world_simulation":d["world"]["simulation"],"radar":radar,"runtime":runtime,"sensors":p["sensors"],
        "rules":d["objectives"],"evaluation":d["evaluation"],"randomization":d["randomization"],"permissions":d["permissions"],"visualization":d["visualization"],
        "tutorial":d["tutorial"],"scaffolding":d["scaffolding"],"metadata":meta}
    return definition


def discover(config):
    settings=config["level_plugins"];directory=ROOT/settings["directory"]
    files=sorted([*directory.glob("*.yaml"),*directory.glob("*.yml")])
    if not files:raise LevelValidationError(directory,"$","no level YAML files found")
    if len(files)>settings["limits"]["max_files"]:raise LevelValidationError(directory,"$","too many level files")
    validator=Validator(config,"level-loader")
    entries=[];ids=set();orders=set()
    for path in files:
        value=read_definition(path,settings["limits"])
        _validate(value,path,config,validator)
        meta=value["metadata"]
        if meta["id"] in ids:raise LevelValidationError(path,"metadata.id","duplicate level ID")
        if meta["order"] in orders:raise LevelValidationError(path,"metadata.order","duplicate progression order")
        ids.add(meta["id"]);orders.add(meta["order"])
        entries.append((meta["order"],path,_compile(value,_map(value,path,config))))
    entries.sort(key=lambda x:x[0])
    levels={d["metadata"]["id"]:d for _,_,d in entries}
    known=set()
    for _,path,d in entries:
        if not set(d["metadata"]["prerequisites"])<=known:raise LevelValidationError(path,"metadata.prerequisites","unknown, cyclic or later prerequisite")
        known.add(d["metadata"]["id"])
    return levels


def assemble(config):
    levels=discover(config)
    chapters={}
    profiles={}
    for lid,d in levels.items():
        chapter=copy.deepcopy(d["metadata"]["chapter"])
        key=chapter["chapter_id"]
        previous=chapters.setdefault(key,{**chapter,"levels":[]})
        if any(previous[k]!=chapter[k] for k in chapter):raise LevelValidationError(lid,"metadata.chapter","chapter metadata disagrees")
        previous["levels"].append(lid)
        if d["robot_profile"]:
            runtime=d["runtime"]
            profile={k:copy.deepcopy(runtime[k]) for k in ("template_version","manifest","contracts","grants","target_source","managed_files")}
            name=d["robot_profile"]
            if name in profiles and profiles[name]!=profile:raise LevelValidationError(lid,"communication.runtime.profile_id","profile alias collision")
            profiles[name]=profile
    for chapter in config["level_plugins"]["planned_chapters"]:
        chapters.setdefault(chapter["chapter_id"],copy.deepcopy(chapter))
    first=next(iter(levels.values()))
    config["robot_graph"]["profiles"]=profiles
    config["campaign"]={"active_level":None,"levels":levels,"lessons":{lid:copy.deepcopy(d["tutorial"]["lesson"]) for lid,d in levels.items()},
        "chapters":list(chapters.values()),"module_id":first["runtime"]["logical_module"]["module_id"],
        "entry_point":first["runtime"]["logical_module"]["entry_point"],"initial_pose":first["scene"]["initial_pose"],"initial_velocity":first["scene"]["initial_velocity"],
        "outcome_priority":[o["reason"] for o in first["rules"]["outcomes"]],"radar":{}}
    return config
