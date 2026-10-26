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
        if value["chassis_type"]!=name or name not in config["chassis"]:
            raise LevelValidationError(path,"chassis_type","profile must match a registered chassis type")
        body,armor=value["body"],value["armor"]
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
    if set(models)!=set(config["chassis"]):
        raise LevelValidationError("chassis_profiles","chassis_profiles","every registered chassis needs a profile")
    config["chassis_profiles"]=models
    config["rendering"]["chassis_models"]={name:copy.deepcopy(value["visual"]) for name,value in models.items()}
    apply_profiles(config)


def body_for(config,chassis):
    body=copy.deepcopy(config["body"])
    if config.get("chassis_profiles"):
        body.update(config["chassis_profiles"][chassis]["body"])
    return body


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


def apply_profiles(config):
    """Resolve the selected player model and per-target geometry into the private Core DTO."""
    if not config.get("chassis_profiles"):
        return config
    config["body"]=body_for(config,config["scene"]["default_chassis"])
    for target in config["weapons"]["targets"]:
        chassis=target.get("motion",{}).get("chassis",config["scene"]["default_chassis"])
        body=body_for(config,chassis)
        if body!=config["body"]:
            target["body"]=body
        else:
            target.pop("body",None)
    return config
