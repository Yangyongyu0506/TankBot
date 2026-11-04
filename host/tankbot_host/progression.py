"""Shared campaign prerequisites and read-only progress inspection; no runtime objects."""
from datetime import datetime
from pathlib import Path


class LevelProgression:
    """The same catalogue rules serve the launcher and offline inspection."""

    def __init__(self, config):
        levels = config.get("campaign", {}).get("levels", {})
        self.levels = list(levels)
        self.prerequisites = {key: value["metadata"]["prerequisites"] for key, value in levels.items()}
        self.level_titles = {key: value["title"] for key, value in levels.items()}
        self.initial_level = next((lid for lid in self.levels if not self.prerequisites[lid]), None)

    def new_progress(self):
        return {"version": 1, "completed_levels": [], "current_level": self.initial_level, "completions": {}}

    def missing_prerequisites(self, level_id, completed):
        done = set(completed)
        return [lid for lid in self.prerequisites[level_id] if lid not in done]

    def unlocked_levels(self, completed):
        return [lid for lid in self.levels if not self.missing_prerequisites(lid, completed)]

    def locked_message(self, level_id, completed):
        missing = self.missing_prerequisites(level_id, completed)
        return "LEVEL_LOCKED: 尚未通关前置关卡：" + "、".join(f"{self.level_titles[lid]} ({lid})" for lid in missing) + "。"

    def load_progress(self, path):
        from tankbot_protocol.wire import strict_loads
        raw = Path(path).read_bytes()
        if len(raw) > 65536:
            raise ValueError("存档文件过大。")
        return self.validate_progress(strict_loads(raw))

    def validate_progress(self, value):
        if (not isinstance(value, dict) or set(value) != {"version", "completed_levels", "current_level", "completions"}
                or type(value["version"]) is not int or value["version"] != 1
                or not isinstance(value["completed_levels"], list) or not isinstance(value["completions"], dict)):
            raise ValueError("存档格式错误；请恢复备份，原文件未被重置。")
        completed = value["completed_levels"]
        if (completed != [lid for lid in self.levels if lid in completed] or len(completed) > len(self.levels)
                or any(self.missing_prerequisites(lid, completed) for lid in completed if lid in self.prerequisites)
                or set(value["completions"]) != set(completed)
                or value["current_level"] not in self.levels + [None]):
            raise ValueError("存档关卡顺序无效；原文件未被重置。")
        for record in value["completions"].values():
            if not isinstance(record, dict) or set(record) != {"completed_at"} or not isinstance(record["completed_at"], str):
                raise ValueError("存档通关记录无效；原文件未被重置。")
            datetime.fromisoformat(record["completed_at"])
        if value["current_level"] is not None and value["current_level"] not in self.unlocked_levels(completed):
            raise ValueError("存档中的当前关卡尚未解锁；原文件未被重置。")
        return value


def format_level_tree(progression, progress):
    """Display every prerequisite edge; shared descendants are only expanded once."""
    completed = progress["completed_levels"]
    unlocked = set(progression.unlocked_levels(completed))
    children = {lid: [] for lid in progression.levels}
    for lid in progression.levels:
        for parent in progression.prerequisites[lid]:
            children[parent].append(lid)
    lines = [f"关卡进度依赖树（已通关 {len(completed)} / {len(progression.levels)}）",
             "连线表示必须通关的前置；多项前置须全部完成。"]
    expanded = set()

    def visit(lid, prefix, connector):
        state = "已通关" if lid in completed else "可挑战" if lid in unlocked else "未解锁"
        tags = [state]
        if lid == progress["current_level"]:
            tags.append("当前关卡")
        missing = progression.missing_prerequisites(lid, completed)
        if missing:
            tags.append("缺少：" + "、".join(missing))
        if len(progression.prerequisites[lid]) > 1:
            tags.append("需全部通关：" + "、".join(progression.prerequisites[lid]))
        if lid in expanded:
            tags.append("同一节点，已在上方展开")
        lines.append(f"{prefix}{connector}{lid}  {progression.level_titles[lid]}  [{'；'.join(tags)}]")
        if lid in expanded:
            return
        expanded.add(lid)
        child_prefix = prefix + ("    " if connector == "└── " else "│   " if connector else "")
        for index, child in enumerate(children[lid]):
            visit(child, child_prefix, "└── " if index == len(children[lid]) - 1 else "├── ")

    roots = [lid for lid in progression.levels if not progression.prerequisites[lid]]
    for lid in roots:
        visit(lid, "", "")
    if not roots:
        lines.append("此配置没有教学关卡。")
    return "\n".join(lines)
