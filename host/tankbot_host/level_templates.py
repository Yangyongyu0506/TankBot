"""Registered player scaffolds, selected by data; plugins cannot supply executable code."""
import ast
from . import campaign_templates as basic
from . import weapon_templates as weapons

COMPONENTS = {
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
