"""Local settings and campaign progress. Never exposed to the player Python runtime."""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
ACTIONS = ("forward", "backward", "left", "right", "turn_left", "turn_right",
           "turret_left", "turret_right", "fire", "editor", "help", "settings")
KEY_CODE = r"Key[A-Z]|Digit[0-9]|Arrow(?:Up|Down|Left|Right)|Space|F(?:[1-9]|1[0-2])|Numpad[0-9]"
LEGACY_LAYERS = ("map", "robot", "trail", "target_estimates", "radar", "imu", "encoders", "turret",
          "truth_robot", "truth_targets", "projectiles", "frames", "velocities", "colliders")
LAYERS = (*LEGACY_LAYERS, "gps", "pose_estimates", "pose_covariance")


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != {"version", "developer_mode", "keyboard", "layers"} or type(value["version"]) is not int or value["version"] != 1 or type(value["developer_mode"]) is not bool:
        raise ValueError("设置文件格式错误：需要 version: 1、developer_mode、keyboard 和 layers。")
    keys = value["keyboard"]
    if not isinstance(keys, dict) or set(keys) != set(ACTIONS):
        raise ValueError("键位映射必须包含所有操作。")
    if any(not isinstance(code, str) or not re.fullmatch(KEY_CODE, code) for code in keys.values()):
        raise ValueError("不支持此按键；请使用字母、数字、方向键、空格或 F1–F12。")
    if len(set(keys.values())) != len(keys):
        raise ValueError("多个操作不能使用同一个按键。")
    if (not isinstance(value["layers"], dict) or not set(LEGACY_LAYERS) <= set(value["layers"]) <= set(LAYERS)
            or any(type(v) is not bool for v in value["layers"].values())):
        raise ValueError("图层设置必须为完整的布尔开关列表。")
    normalized = copy.deepcopy(value)
    for layer in LAYERS:
        normalized["layers"].setdefault(layer, False)
    return normalized


def load_settings(path):
    import yaml
    # Duplicate keys should fail rather than silently change a binding/mode.
    class Loader(yaml.SafeLoader):
        pass
    def mapping(loader, node):
        result = {}
        for key, value in node.value:
            name = loader.construct_object(key, deep=True)
            if not isinstance(name, str) or name in result:
                raise ValueError("设置 YAML 含重复或非字符串键。")
            result[name] = loader.construct_object(value, deep=True)
        return result
    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    raw = Path(path).read_bytes()
    if len(raw) > 8192:
        raise ValueError("设置 YAML 文件过大。")
    try:
        return validate_settings(yaml.load(raw, Loader=Loader))
    except (yaml.YAMLError, RecursionError) as error:
        raise ValueError("设置 YAML 无效；请检查文件内容。") from error


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class ApplicationState:
    """One local profile; OS file locks and atomic replacement protect concurrent launchers."""
    def __init__(self, config, settings_path=None, progress_path=None):
        self.settings_path = Path(settings_path or ROOT / "userdata/settings.yaml")
        self.progress_path = Path(progress_path or ROOT / "userdata/progress.json")
        if self.settings_path.resolve() == self.progress_path.resolve():
            raise ValueError("设置文件和存档文件必须使用不同路径。")
        self.levels = list(config.get("campaign", {}).get("levels", {}))
        self.prerequisites={key:value["metadata"]["prerequisites"] for key,value in config.get("campaign",{}).get("levels",{}).items()}
        self.level_titles={key:value["title"] for key,value in config.get("campaign",{}).get("levels",{}).items()}
        self.initial_level=next((lid for lid in self.levels if not self.prerequisites[lid]),None)
        self.lock = threading.RLock()
        self.tickets = {}
        self.defaults = load_settings(ROOT / "config/settings.yaml")
        with self.transaction(self.settings_path):
            if not self.settings_path.exists():
                self.write_settings(self.defaults)
            self.settings = load_settings(self.settings_path)
        with self.transaction(self.progress_path):
            if not self.progress_path.exists():
                self.write(self.progress_path, {"version": 1, "completed_levels": [], "current_level": self.initial_level, "completions": {}})
            self.read_progress()

    @contextmanager
    def transaction(self, path):
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with Path(str(path) + ".lock").open("a+b") as handle:
                if os.name == "nt":
                    import msvcrt
                    if handle.tell() == 0:
                        handle.write(b"0"); handle.flush()
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if os.name == "nt":
                        handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def write(path, value, *, yaml_format=False):
        if yaml_format:
            import yaml
            raw = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
        else:
            raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def write_settings(self, value):
        self.write(self.settings_path, value, yaml_format=True)

    @property
    def developer(self):
        return self.settings["developer_mode"]

    def public_settings(self):
        with self.lock:
            return {"settings": copy.deepcopy(self.settings), "revision": revision(self.settings),
                    "defaults": copy.deepcopy(self.defaults), "settings_file": str(self.settings_path),
                    "progress_file": str(self.progress_path)}

    def update_settings(self, value):
        if not isinstance(value, dict) or set(value) != {"revision", "settings"}:
            raise ValueError("INVALID_SETTINGS_REQUEST")
        candidate = validate_settings(value["settings"])
        if not candidate["developer_mode"] and not self.levels:
            raise ValueError("当前配置没有教学关卡，无法切换为玩家模式；请使用包含 Campaign 的配置。")
        with self.transaction(self.settings_path):
            if revision(load_settings(self.settings_path)) != value["revision"]:
                raise ValueError("设置已被其他窗口修改，请刷新后重试。")
            changed = candidate["developer_mode"] != self.developer
            self.write_settings(candidate)
            self.settings = candidate
            if changed:
                self.tickets.clear()  # An attempt may never cross mode boundaries.
            return {**self.public_settings(), "mode_changed": changed, "reload_required": changed}

    def read_progress(self):
        from tankbot_protocol.wire import strict_loads
        raw = self.progress_path.read_bytes()
        if len(raw) > 65536:
            raise ValueError("存档文件过大。")
        value = strict_loads(raw)
        if (not isinstance(value, dict) or set(value) != {"version", "completed_levels", "current_level", "completions"}
                or type(value["version"]) is not int or value["version"] != 1
                or not isinstance(value["completed_levels"], list) or not isinstance(value["completions"], dict)):
            raise ValueError("存档格式错误；请恢复备份，原文件未被重置。")
        completed = value["completed_levels"]
        if (completed != [lid for lid in self.levels if lid in completed] or len(completed) > len(self.levels)
                or any(self.missing_prerequisites(lid,completed) for lid in completed if lid in self.prerequisites)
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

    def missing_prerequisites(self, level_id, completed):
        done=set(completed)
        return [lid for lid in self.prerequisites[level_id] if lid not in done]

    def unlocked_levels(self, completed):
        return [lid for lid in self.levels if not self.missing_prerequisites(lid,completed)]

    def locked_message(self, level_id, completed):
        missing=self.missing_prerequisites(level_id,completed)
        return "LEVEL_LOCKED: 尚未通关前置关卡："+"、".join(f"{self.level_titles[lid]} ({lid})" for lid in missing)+"。"

    def progress(self):
        with self.transaction(self.progress_path):
            value = self.read_progress()
        return {**value, "unlocked_levels": self.unlocked_levels(value["completed_levels"]), "developer_mode": self.developer}

    def require_level(self, level_id):
        if level_id not in self.levels:
            raise ValueError("UNKNOWN_LEVEL")
        if not self.developer:
            completed=self.progress()["completed_levels"]
            if self.missing_prerequisites(level_id,completed):
                raise ValueError(self.locked_message(level_id,completed))

    def select_level(self, level_id):
        self.require_level(level_id)
        if not self.developer:
            with self.transaction(self.progress_path):
                value = self.read_progress(); value["current_level"] = level_id
                self.write(self.progress_path, value)

    def register_attempt(self, level_id, run_id=None, *, practice=False):
        self.require_level(level_id)
        with self.lock:
            ticket = run_id or secrets.token_urlsafe()
            # Bound memory for reloads; old browser tabs must restart after revocation.
            if len(self.tickets) >= 128:
                self.tickets.pop(next(iter(self.tickets)))
            self.tickets[ticket] = (level_id, self.developer, bool(practice))
            return ticket

    def complete(self, ticket, level_id):
        with self.lock:
            attempt = self.tickets.get(ticket)
            if attempt is None or attempt[:2] != (level_id, self.developer):
                raise ValueError("ATTEMPT_REVOKED: 请重新开始关卡。")
            if not self.developer and not attempt[2]:
                with self.transaction(self.progress_path):
                    value = self.read_progress()
                    if level_id not in value["completed_levels"]:
                        if self.missing_prerequisites(level_id,value["completed_levels"]):
                            raise ValueError(self.locked_message(level_id,value["completed_levels"]))
                        value["completed_levels"].append(level_id)
                        value["completed_levels"].sort(key=self.levels.index)
                        value["completions"][level_id] = {"completed_at": datetime.now(timezone.utc).isoformat()}
                        self.write(self.progress_path, value)
            return self.progress()
