"""Trusted reusable chassis geometry; physics, teaching and rendering share mounts."""
import copy
import math

GEOMETRY_FIELDS=("length_m","width_m","corner_radius_m")


def side_mounts(body):
    return [[body["length_m"]/2,0.,0.],[-body["length_m"]/2,0.,-math.pi],
            [0.,body["width_m"]/2,math.pi/2],[0.,-body["width_m"]/2,-math.pi/2]]


def load_profiles(config):
    from .authority import ROOT
    from .level_plugins import read_definition,LevelValidationError,error_path
    from tankbot_protocol.validation import Validator
    specs=config.get("chassis_profiles")
    if specs is None:
        return
    if "wheels" in config:
        from .wheel_geometry import validate_wheels
        try:validate_wheels(config["wheels"])
        except (KeyError,TypeError) as error:raise ValueError("Incomplete wheel calibration") from error
    if not isinstance(specs,dict) or not specs:
        raise LevelValidationError("chassis_profiles","chassis_profiles","expected a nonempty model mapping")
    root=(ROOT/"config/chassis").resolve()
    schemas=Validator(config,"chassis-loader").schemas
    validator=schemas["chassis-profile.schema.json"]
    models={}
    for name,source in specs.items():
        if isinstance(source,dict):
            value=copy.deepcopy(source);path="chassis_profiles."+name
        elif isinstance(source,str):
            path=(ROOT/source).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise LevelValidationError(path,"chassis_profiles."+name,"chassis asset must exist inside config/chassis/")
            value=read_definition(path,config["level_plugins"]["limits"])
        else:
            raise LevelValidationError("chassis_profiles",name,"expected an asset path or compiled profile")
        errors=list(validator.iter_errors(value))
        if errors:
            error=errors[0];raise LevelValidationError(path,error_path(error.absolute_path),error.message)
        if value["chassis_type"]!=name or name not in ("differential","omnidirectional"):
            raise LevelValidationError(path,"chassis_type","profile must match a registered chassis type")
        if "motor" in value and (name!="differential" or value["schema_version"]!="2.0"):
            raise LevelValidationError(path,"motor","DC wheel voltage is supported only by the complete differential model")
        body,armor=value["body"],value["armor"]
        if value["schema_version"]=="2.0":
            lateral=name=="omnidirectional"
            if value["drive"]["lateral_actuation"]!=lateral or ("track_m" in value["wheels"])==lateral:
                raise LevelValidationError(path,"wheels","wheel layout and lateral actuation must match chassis_type")
        tolerance=config["validation"]["numeric_tolerance"]
        if 2*body["corner_radius_m"]>=min(body["length_m"],body["width_m"]):
            raise LevelValidationError(path,"body.corner_radius_m","rounding must fit the body")
        if armor["width_m"]>min(body["length_m"],body["width_m"])-2*body["corner_radius_m"]:
            raise LevelValidationError(path,"armor.width_m","armor must fit the straight side surface")
        expected=side_mounts(body)
        if any(abs(a-b)>tolerance for row,want in zip(armor["mounts_m"],expected) for a,b in zip(row,want)):
            raise LevelValidationError(path,"armor.mounts_m","four side centers must lie on the actual body surface in front/back/left/right order")
        if value["gps_mount_m"]!=expected[0][:2]:
            raise LevelValidationError(path,"gps_mount_m","front GPS must share the front-center installation")
        visual=value["visual"]
        visual_schema=copy.deepcopy(schemas["simulation-profile.schema.json"].schema["properties"]["rendering"]["properties"]["chassis_models"]["properties"][name])
        if name=="omnidirectional":
            shell_schema=visual_schema["properties"]["armor"]
            shell_schema["required"]=[key for key in shell_schema["required"] if key not in ("front_center_x_m","side_center_y_m")]
        from jsonschema import Draft202012Validator
        visual_errors=list(Draft202012Validator(visual_schema).iter_errors(visual))
        if visual_errors:
            error=visual_errors[0];raise LevelValidationError(path,"visual."+error_path(error.absolute_path),error.message)
        if visual.get("kind")=="radial_omni" and "armor" in visual:
            # Decorative armor shells terminate at the same physical mounting
            # planes. Positions are derived, not another editable geometry source.
            shell=visual["armor"]
            shell["front_center_x_m"]=body["length_m"]/2-shell["front_length_m"]/2
            shell["side_center_y_m"]=body["width_m"]/2-shell["side_width_m"]/2
        models[name]=value
    if set(models)!={"differential","omnidirectional"}:
        raise LevelValidationError("chassis_profiles","chassis_profiles","every registered chassis needs a profile")
    config["chassis_profiles"]=models
    if all(m["schema_version"]=="2.0" for m in models.values()):
        config["chassis"]={name:copy.deepcopy(m["drive"]) for name,m in models.items()}
    elif any(m["schema_version"]=="2.0" for m in models.values()):
        raise LevelValidationError("chassis_profiles","schema_version","cannot mix complete and legacy geometry models")
    config["rendering"]["chassis_models"]={name:copy.deepcopy(value["visual"]) for name,value in models.items()}
    apply_profiles(config,dynamics=True)


def body_for(config,chassis):
    body=copy.deepcopy(config["body"])
    if config.get("chassis_profiles"):
        body.update(config["chassis_profiles"][chassis]["body"])
    return body


def wheel_calibration_for(config,chassis):
    from .wheel_geometry import public_calibration
    model=config.get("chassis_profiles",{}).get(chassis,{})
    if model.get("schema_version")=="2.0" and chassis=="omnidirectional":
        return copy.deepcopy(model["wheels"])
    return public_calibration(config["wheels"])


def target_geometry(config,target=None):
    target=target or (config["weapons"]["targets"][0] if config["weapons"]["targets"] else {})
    chassis=target.get("motion",{}).get("chassis",config["scene"]["default_chassis"])
    body=target.get("body",body_for(config,chassis))
    armor=target.get("armor")
    mounts=armor.get("mounts_m",side_mounts(body)) if armor else []
    profile=config.get("chassis_profiles",{}).get(chassis)
    return {"body":{key:body[key] for key in GEOMETRY_FIELDS},
            "armor_width_m":armor["width_m"] if armor else None,"armor_mounts":copy.deepcopy(mounts),
            "gps_mount_m":copy.deepcopy(profile["gps_mount_m"]) if profile else [body["length_m"]/2,0.]}


def apply_profiles(config, *, dynamics=False):
    """Resolve the selected player model and per-target geometry into the private Core DTO."""
    if not config.get("chassis_profiles"):
        return config
    name=config["scene"]["default_chassis"]
    model=config["chassis_profiles"][name]
    dynamics=dynamics or config.get("selected_chassis_model")!=name
    if dynamics and model["schema_version"]=="2.0":
        config["selected_chassis_model"]=name
        config["body"]=copy.deepcopy(model["body"])
        for key in ("servo","motion_limits","controller"):
            config[key]=copy.deepcopy(model[key])
        diff=config["chassis_profiles"]["differential"]["wheels"]
        omni=copy.deepcopy(config["chassis_profiles"]["omnidirectional"]["wheels"])
        omni.pop("radius_m")
        config["wheels"]={"radius_m":model["wheels"]["radius_m"],"differential_track_m":diff["track_m"],"omnidirectional":omni}
    config["body"]=body_for(config,name)
    for target in config["weapons"]["targets"]:
        chassis=target.get("motion",{}).get("chassis",config["scene"]["default_chassis"])
        body=body_for(config,chassis)
        if body!=config["body"]:
            target["body"]=body
        else:
            target.pop("body",None)
        enemy=config["chassis_profiles"][chassis]
        if enemy["schema_version"]=="2.0":
            for key in ("servo","motion_limits"):
                if enemy[key]!=config[key]:target[key]=copy.deepcopy(enemy[key])
                else:target.pop(key,None)
    return config
