"""Registered player scaffolds, selected by data; plugins cannot supply executable code."""
import ast
from . import campaign_templates as basic
from . import weapon_templates as weapons
from . import weapon_curriculum as curriculum

COMPONENTS = {
    "armor_tracker":{"perception/__init__.py":"","perception/armor_tracker.py":curriculum.ARMOR_TRACKER},
    "armor_tracking_adapter":{"robot_modules/__init__.py":"","robot_modules/armor_observations.py":curriculum.ARMOR_ADAPTER},
    "armor_contract_tests":{"tests/test_armor_contract.py":curriculum.ARMOR_TEST},
    "campaign_adapter":{"campaign_robot.py":basic.WRAPPER},
    "empty_perception_package":{"perception/__init__.py":""},
    "se3_transform":{"perception/__init__.py":"","perception/transforms.py":basic.TRANSFORMS},
    "se3_tests":{"tests/test_coordinates.py":basic.COORDINATE_TEST},
    "point_tracker":{"perception/tracker.py":basic.TRACKER},
    "weapons_adapters":{"robot_modules/__init__.py":"","robot_modules/weapons.py":weapons.MODULES,"perception/__init__.py":"","weapons/__init__.py":""},
    "auto_aim":{"weapons/auto_aim.py":weapons.AUTO_AIM},
    "armor_aim":{"weapons/armor_aim.py":weapons.ARMOR_AIM},
    "pose_tracker":{"perception/pose_tracker.py":weapons.POSE_TRACKER},
    "auto_aim_tests":{"tests/test_auto_aim.py":weapons.TEST},
    "polar_tracker":{"perception/__init__.py":"","perception/polar_tracker.py":curriculum.POLAR_TRACKER},
    "fusion_tracker":{"perception/fusion_tracker.py":curriculum.FUSION_TRACKER},
    "raw_sensor_adapters":{"robot_modules/__init__.py":"","robot_modules/observations.py":curriculum.RAW_ADAPTERS},
    "predictive_aiming_adapter":{"robot_modules/aiming.py":curriculum.PREDICTIVE_ADAPTER,"weapons/__init__.py":""},
    "polar_auto_aim":{"weapons/auto_aim.py":curriculum.POLAR_AUTO_AIM},
    "target_prediction":{"weapons/target_prediction.py":curriculum.TARGET_PREDICTION},
    "polar_contract_tests":{"tests/test_polar_contract.py":curriculum.POLAR_TEST},
    "fusion_contract_tests":{"tests/test_fusion_contract.py":curriculum.FUSION_TEST},
    "predictive_contract_tests":{"tests/test_prediction_contract.py":curriculum.PREDICTIVE_TEST},
}


def sources(definition):
    result={}
    for name in definition["scaffolding"]["components"]:
        result.update(COMPONENTS[name])
    for path,entries in definition["scaffolding"]["documentation"].items():
        source=result[path]
        tree=ast.parse(source)
        replacements=[]
        for entry in entries:
            for node in ast.walk(tree):
                if isinstance(node,ast.FunctionDef) and node.name==entry["function"] and ast.get_docstring(node):
                    expression=node.body[0]
                    indent=" "*expression.col_offset
                    text=entry["text"].replace('\\','\\\\').replace('"""','\\"\\"\\"')
                    replacement=indent+'"""'+text.replace('\n','\n'+indent)+'"""\n'
                    replacements.append((expression.lineno-1,expression.end_lineno,replacement))
        lines=source.splitlines(keepends=True)
        for start,end,replacement in sorted(replacements,reverse=True):lines[start:end]=[replacement]
        result[path]=''.join(lines)
    return result
