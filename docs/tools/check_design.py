"""离线检查设计文档和结构夹具；不实现或执行游戏/SDK/玩家算法。"""

import ast
import copy
import json
import math
import re
from pathlib import Path
from urllib.parse import unquote

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"重复 JSON 键: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"非有限 JSON 数值: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"JSON 浮点溢出: {value}")
        return number

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant,
                      parse_float=finite_float)


def schema_for(value):
    if "message_type" in value:
        return "envelope.schema.json", None
    if "geometry_version" in value:
        return "wheel-calibration.schema.json", None
    if "manifest_version" in value:
        return "workspace.schema.json", None
    if "contract_version" in value:
        return "module-contract.schema.json", None
    if "system_pose_allowed" in value:
        return "view-policy.schema.json", None
    if "linear" in value and "angular" in value:
        return "payloads.schema.json", "twist"
    if "controller_profile_version" in value:
        return "chassis-controller.schema.json", None
    if "config_version" in value:
        return "simulation-profile.schema.json", None
    if "activation_tick" in value:
        return "payloads.schema.json", "runtime_step_request"
    if "step_id" in value and "results" in value:
        return "payloads.schema.json", "runtime_step_result"
    return None


def main():
    for invalid in ('{"a":1,"a":2}', '{"value":NaN}', '{"value":1e999}'):
        try:
            strict_json(invalid)
        except ValueError:
            pass
        else:
            raise ValueError(f"严格解析未拒绝非法数据: {invalid}")
    schemas = {
        path.name: strict_json(path.read_text(encoding="utf-8"))
        for path in sorted((DOCS / "schemas").glob("*.schema.json"))
    }
    for path in (DOCS / "schemas").glob("*.json"):
        value = strict_json(path.read_text(encoding="utf-8"))
        assert path.read_text(encoding="utf-8") == json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", f"非规范 JSON 格式: {path}"
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in schemas.values()
    )
    validators = {}
    for filename, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        validators[(filename, None)] = Draft202012Validator(schema, registry=registry)
    validators[("simulation-profile.schema.json", None)].validate(strict_json((ROOT/"config/m1.json").read_text()))
    for name in schemas["payloads.schema.json"]["$defs"]:
        reference = schemas["payloads.schema.json"]["$id"] + "#/$defs/" + name
        validators[("payloads.schema.json", name)] = Draft202012Validator(
            {"$ref": reference}, registry=registry
        )

    examples = {}
    for path in sorted((DOCS / "examples").glob("*.json")):
        value = strict_json(path.read_text(encoding="utf-8"))
        examples[path.name] = value
        assert path.read_text(encoding="utf-8") == json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", f"非规范 JSON 格式: {path}"
        selected = schema_for(value)
        if selected:
            validators[selected].validate(value)

    schema_cases = domain_cases = 0
    for case in examples["validation-cases.json"]["cases"]:
        value = copy.deepcopy(examples[case["fixture"]])
        selected = schema_for(value)
        mutations = case["mutations"] if "mutations" in case else [case["mutation"]]
        for mutation in mutations:
            keys = [key.replace("~1", "/").replace("~0", "~")
                    for key in mutation["pointer"].split("/")[1:]]
            target = value
            for key in keys[:-1]:
                target = target[int(key)] if isinstance(target, list) else target[key]
            final_key = int(keys[-1]) if isinstance(target, list) else keys[-1]
            target[final_key] = mutation["value"]
        errors = list(validators[selected].iter_errors(value))
        if case["layer"] == "schema":
            assert errors, f"结构负例未被拒绝: {case['case_id']}"
            schema_cases += 1
        else:
            assert not errors, f"领域负例被结构层提前拒绝: {case['case_id']}"
            domain_cases += 1

    markdown = sorted(DOCS.rglob("*.md")) + [ROOT / "README.md", ROOT / "AGENTS.md"]
    json_blocks = python_blocks = local_links = 0
    canonical = {
        "03_PROTOCOL_SPECIFICATION.md": [("pose-message.json", None), ("cmd-vel-message.json", "payload"), ("chassis-controller.json", None)],
        "04_STATE_AND_VIEW_MODEL.md": [("view-policy.json", None)],
        "05_ROBOT_MODULE_SYSTEM.md": [("module-contract.json", None)],
        "06_WORKSPACE_AND_TEMPLATES.md": [("tankbot.json", None)],
    }
    for path in markdown:
        text = path.read_text(encoding="utf-8")
        assert len(re.findall(r"^```", text, re.M)) % 2 == 0, f"未闭合代码块: {path}"
        file_json = []
        for language, code in re.findall(r"^```(\w*)\n(.*?)^```", text, re.M | re.S):
            if language == "json":
                value = strict_json(code)
                file_json.append(value)
                selected = schema_for(value)
                if selected:
                    validators[selected].validate(value)
                json_blocks += 1
            elif language == "python":
                ast.parse(code)
                python_blocks += 1
        if path.name in canonical:
            expected = [examples[name] if key is None else examples[name][key]
                        for name, key in canonical[path.name]]
            assert file_json == expected, f"正文与规范夹具不一致: {path}"
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0].strip("<>"))
            assert (path.parent / target).exists(), f"失效本地链接: {path}: {target}"
            local_links += 1
        assert text.endswith("\n"), f"缺少末尾换行: {path}"
        assert all(line == line.rstrip() for line in text.splitlines()), f"行尾空白: {path}"

    index = (DOCS / "adr" / "README.md").read_text(encoding="utf-8")
    states = {"Accepted": 0, "Proposed": 0, "Superseded": 0}
    for path in sorted((DOCS / "adr").glob("[0-9]*.md")):
        status = re.findall(r"^- Status: (Accepted|Proposed|Superseded)$", path.read_text(encoding="utf-8"), re.M)
        assert len(status) == 1, f"ADR 状态错误: {path}"
        assert any(path.name in row and f"| {status[0]} |" in row for row in index.splitlines()), f"ADR 索引状态不一致: {path}"
        states[status[0]] += 1

    print(f"PASS: {len(markdown)} Markdown files, {local_links} local links, {len(schemas)} Schemas")
    print(f"PASS: {len(examples) - 1} positive fixtures, {schema_cases} rejected structural cases")
    print(f"PASS: {json_blocks} JSON blocks, {python_blocks} Python syntax blocks; ADR states: {states}")
    print(f"STRUCTURE ONLY: {domain_cases} domain cases; real M1 coverage is in tests/test_protocol_fixtures.py and tests/test_m1.py")


if __name__ == "__main__":
    main()
