"""Bundled teaching scaffolds. Never execute these helpers in a player Runtime."""
from .template_resources import load_template_resource
import ast
import json
import re

TEMPLATE_VERSION: str = "1.2.0"

WRAPPER: str = load_template_resource("common/campaign_robot.py")

TRANSFORMS: str = load_template_resource("weapons/transforms.py")

TRACKER: str = load_template_resource("weapons/tracker.py")

COORDINATE_TEST: str = load_template_resource("weapons/test_coordinates.py")


MANAGED_FILES: tuple[str, ...] = ("campaign_robot.py", "tankbot.json", "contracts/perception.json", "tests/test_coordinates.py")


def template_version(config: dict) -> str:
    level = config.get("campaign", {}).get("active_level")
    return config["campaign"]["levels"][level]["runtime"]["template_version"] if level else TEMPLATE_VERSION


def scaffold_api(source: str, class_name: str) -> str | None:
    """Read a managed adapter's API declaration without importing player code."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
                        and item.target.id == "scaffold_api" and isinstance(item.value, ast.Constant)
                        and isinstance(item.value.value, str)):
                    return item.value.value
    return None


def generated_algorithm_updates(config: dict, files: dict[str, str], ledger: dict) -> list[str]:
    """Only offer old, untouched generated stubs; never infer ownership from a TODO."""
    level = config.get("campaign", {}).get("active_level")
    if not level:
        return []
    from .level_templates import sources
    definition = config["campaign"]["levels"][level]
    incoming = sources(definition)
    managed = set(definition["runtime"].get("managed_files", []))
    lesson = definition["tutorial"]["lesson"]
    editable = set(lesson.get("edit_files", [item["path"] for item in lesson["functions"]]))
    generated = [entry.get("files", {}) for key,entry in ledger.items()
                 if key.startswith("campaign-")]
    def implementation(source):
        try:
            tree=ast.parse(source)
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if isinstance(node,(ast.Module,ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and ast.get_docstring(node) is not None:
                node.body=node.body[1:]
        return ast.dump(tree)
    return sorted(path for path in editable if path not in managed and path in files
                  and path in incoming and files[path] != incoming[path]
                  and implementation(files[path]) is not None
                  and implementation(files[path]) != implementation(incoming[path])
                  and any(old.get(path) == files[path] for old in generated))


def framework_upgrade(config: dict, files: dict[str, str], ledger: dict | None = None) -> dict:
    """One compatibility check for the editor and Test; comments are not an API."""
    level = config.get("campaign",{}).get("active_level")
    profile_name = config["campaign"]["levels"][level].get("robot_profile") if level else None
    if profile_name:
        profile = config["robot_graph"]["profiles"][profile_name]
        try:
            manifest = json.loads(files.get("tankbot.json","{}"))
            current = bool(manifest.get("modules")) and all(item["contract"] in files for item in manifest["modules"])
            # A one-shot task is declared separately from periodic modules. An
            # older project's manifest is upgraded only through the preview.
            expected_preparation=profile["manifest"].get("preparation")
            if expected_preparation is not None:
                current &= manifest.get("preparation")==expected_preparation
            if current:
                declared={item["module_id"]:json.loads(files[item["contract"]]) for item in manifest["modules"]}
                source=manifest.get("pose_source",{})
                policy=config["view_policy"]
                if source.get("mode")=="system":
                    current &= policy["system_pose_allowed"]
                elif source.get("mode")=="player":
                    current &= policy["player_pose_allowed"]
                for connection in manifest.get("connections",[]):
                    if not connection["from"].startswith("/") and connection["to"].startswith("/robot/estimates/"):
                        mid,port=connection["from"].split(".")
                        current &= declared[mid]["outputs"][port]["schema"] in profile["grants"]["outputs"]
            managed_projects = {p["manifest"]["project_id"] for p in config["robot_graph"]["profiles"].values()}
            if current and manifest.get("project_id") in managed_projects:
                current &= {m["module_id"] for m in manifest["modules"]} == set(profile["contracts"])
                # Port types and managed Python adapter APIs can evolve independently.
                from .level_templates import sources
                expected_files = sources(config["campaign"]["levels"][level])
                for item in manifest["modules"]:
                    expected = profile["contracts"].get(item["module_id"])
                    if expected and item["contract"] == f"contracts/{item['module_id']}.json":
                        contract = json.loads(files[item["contract"]])
                        current &= all({p:v["schema"] for p,v in contract[field].items()} ==
                                       {p:v["schema"] for p,v in expected[field].items()} for field in ("inputs","outputs"))
                        if contract["entry_point"] == expected["entry_point"]:
                            module_path, class_name = expected["entry_point"].split(":")
                            path = module_path.replace(".", "/") + ".py"
                            api = scaffold_api(expected_files.get(path, ""), class_name)
                            if api is not None:
                                try:
                                    current &= scaffold_api(files.get(path, ""), class_name) == api
                                except SyntaxError:
                                    pass  # Test must report source syntax errors normally.
        except (ValueError,KeyError,TypeError):
            current = False
        generated = generated_algorithm_updates(config,files,ledger or {})
        message = ("发现仍未修改的旧算法模板："+"、".join(generated)+"。请预览更新输入接口；已编写的算法文件保留。"
                   if generated else "本关的模块连接或显示权限已变化；请预览系统脚手架升级，已有算法文件完整保留。" if not current else "")
        return {"required":not current or bool(generated),"current_version":None,"target_version":profile["template_version"],
                "managed_files":profile["managed_files"],"generated_algorithm_files":generated,"message":message}
    source: str = files.get("campaign_robot.py", "")
    marker: re.Match | None = re.search(r"^\s*# TankBot managed scaffold ([0-9.]+)(?:\s|$)", source, re.MULTILINE)
    current: bool = marker is not None and marker.group(1) == TEMPLATE_VERSION
    if not current:
        try:
            # A deleted version comment or formatting-only edit must not block valid code.
            current = ast.dump(ast.parse(source)) == ast.dump(ast.parse(WRAPPER))
        except SyntaxError:
            current = True  # Let Test report the syntax error before classifying framework compatibility.
    manifest_mismatch = False
    if level and "tankbot.json" in files:
        try:
            manifest = json.loads(files["tankbot.json"])
            modules = manifest.get("modules")
            expected = config["campaign"]["levels"][level]["runtime"]["manifest"]["modules"]
            # A compatible wrapper can survive a later lesson's graph upgrade.
            # Check the active declaration too, without rewriting any player files.
            if isinstance(modules,list) and modules and all(isinstance(item,dict) and isinstance(item.get("module_id"),str) for item in modules):
                manifest_mismatch = len(modules)!=1 or modules[0]["module_id"]!=expected[0]["module_id"]
                current &= not manifest_mismatch
        except (ValueError,AttributeError,TypeError):
            pass  # Invalid manifests still belong to the ordinary Schema validator.
    required: bool = bool(config.get("campaign", {}).get("active_level") and not current)
    return {"required": required, "current_version": marker.group(1) if marker else None,
            "target_version": TEMPLATE_VERSION, "managed_files": config["campaign"]["levels"][level]["runtime"]["managed_files"] if level else list(MANAGED_FILES),
            "message": ("当前工作区的模块配置与本关不匹配；本关使用单模块框架。请预览并切换本关运行配置，已有算法文件和历史版本会保留。"
                        if manifest_mismatch else "当前项目的课程运行框架需要更新，算法尚未开始测试。预览后可保留算法文件，更新框架并继续测试。") if required else ""}
