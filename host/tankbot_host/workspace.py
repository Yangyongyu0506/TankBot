"""Versioned local workspace: immutable revisions, explicit edits and non-overwriting templates."""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid
from tankbot_protocol.wire import strict_loads

ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def artifact_files(files):
    return {p: s for p, s in files.items()
            if (p.endswith(".py") and not p.startswith(("tests/", "data/")))
            or p == "tankbot.json" or (p.startswith("contracts/") and p.endswith(".json"))}


def validate_files(files, limits):
    if not isinstance(files, dict) or not files or len(files) > limits["max_files"]:
        raise ValueError("WORKSPACE_FILE_LIMIT")
    seen = set()
    for path, source in files.items():
        if not isinstance(path, str) or len(path) > 160 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*\.(py|json|md)", path):
            raise ValueError("UNSAFE_PATH")
        parts = path.split("/")
        if any(p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))} for p in parts):
            raise ValueError("RESERVED_PATH")
        if path.casefold() in seen or not isinstance(source, str) or "\x00" in source:
            raise ValueError("INVALID_SOURCE")
        seen.add(path.casefold())
    if sum(len(p.encode()) + len(s.encode()) for p, s in files.items()) > limits["max_source_bytes"]:
        raise ValueError("WORKSPACE_BYTE_LIMIT")
    # A file may not also be a parent directory, including on case-insensitive hosts.
    for path in seen:
        if any("/".join(path.split("/")[:i]) in seen for i in range(1, len(path.split("/")))):
            raise ValueError("PATH_COLLISION")


def read_sources(root, limits):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("UNSAFE_WORKSPACE_ROOT")
    root = root.resolve()
    files = {}
    for p in root.rglob("*"):
        relative = p.relative_to(root)
        if any(x.startswith(".") or x == "__pycache__" for x in relative.parts):
            continue
        mode = p.lstat()
        if stat.S_ISLNK(mode.st_mode):
            raise ValueError("SYMLINK_NOT_ALLOWED")
        if p.is_dir():
            continue
        if p.suffix not in (".py", ".json", ".md"):
            continue
        if not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1 or mode.st_size > limits["max_source_bytes"]:
            raise ValueError("UNSAFE_SOURCE_FILE")
        files[relative.as_posix()] = p.read_text(encoding="utf-8")
    validate_files(files, limits)
    return files


def starter(config):
    level = config.get("campaign",{}).get("active_level")
    profile_name = config["campaign"]["levels"][level].get("robot_profile") if level else None
    if profile_name:
        from .weapon_templates import sources
        profile = config["robot_graph"]["profiles"][profile_name]
        files = sources(config["campaign"]["levels"][level])
        files["tankbot.json"] = json.dumps(profile["manifest"],indent=2)+"\n"
        for mid,contract in profile["contracts"].items():
            files[f"contracts/{mid}.json"] = json.dumps(contract,indent=2)+"\n"
        return files
    from .module_profile import module_profile
    contract, inputs, outputs = module_profile(config)
    module_id = contract["module_id"]
    manifest = {"manifest_version": "1.0", "sdk_version": "0.1.0", "protocol_version": "1.0",
                "project_id": "my-first-robot", "entry_point": contract["entry_point"],
                "modules": [{"module_id": module_id, "contract": f"contracts/{module_id}.json", "config": {}}],
                "connections": [{"from": channel, "to": f"{module_id}.{port}"} for port, channel in inputs.items()] +
                               [{"from": f"{module_id}.{port}", "to": channel} for port, channel in outputs.items()],
                "dependencies": [], "pose_source": {"mode": "player", "module_id": module_id, "fallback": "none"}}
    level = config.get("campaign", {}).get("active_level")
    if level:
        from .campaign_templates import teaching_sources
        files = teaching_sources(level)
        manifest["pose_source"] = {"mode": "system", "module_id": None, "fallback": "none"}
    else:
        files = read_sources(ROOT / "examples/robot", config["workspace"])
    files["tankbot.json"] = json.dumps(manifest, indent=2) + "\n"
    files[f"contracts/{module_id}.json"] = json.dumps(contract, indent=2) + "\n"
    if not level:
        files["tests/test_project.py"] = 'import unittest\n\nclass ProjectTest(unittest.TestCase):\n    def test_import(self) -> None:\n        from localization.kinematics import body_increment\n        self.assertTrue(callable(body_increment))\n'
    return files


def open_store(config, seed=None, directory=None):
    template = starter(config)
    files = read_sources(seed, config["workspace"]) if seed else template
    # Seed user files always win; missing scaffolding is the only automatic addition.
    files = {**template, **files}
    key = digest({"seed": str(Path(seed).resolve()) if seed else "default", "entry": config["module"]["entry_point"],
                  "sources": config["control_sources"]})[:16]
    return WorkspaceStore(directory or ROOT / ".m1-cache/workspaces" / key, files, config["workspace"])


class WorkspaceStore:
    """All source content lives in immutable JSON revisions; HEAD is atomically replaced.

    The seed directory is read-only. CAS protects multiple tabs; one server owns a store.
    """
    def __init__(self, directory, files, limits):
        self.directory = Path(directory)
        self.limits = limits
        self.lock = threading.RLock()
        self.depth = 0
        self.plans = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        self.head = self.directory / "HEAD.json"
        with self.transaction():
            if not self.head.exists():
                validate_files(files, limits)
                self._write(files, {})

    @contextmanager
    def transaction(self):
        with self.lock:
            handle = None
            if self.depth == 0:
                handle = (self.directory / "LOCK").open("a+b")
                if os.name == "nt":
                    import msvcrt
                    if handle.tell() == 0:
                        handle.write(b"0"); handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
                if handle is not None:
                    if os.name == "nt":
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    handle.close()

    def _write(self, files, ledger):
        value = {"files": files, "ledger": ledger}
        revision = digest(value)
        value["revision"] = revision
        path = self.directory / (revision + ".json")
        raw = json.dumps(value, ensure_ascii=True, indent=2).encode()
        try:
            with path.open("xb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError("REVISION_CORRUPT")
        temporary = self.directory / ("head-" + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as f:
                f.write(json.dumps({"revision": revision}).encode())
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.head)
        finally:
            temporary.unlink(missing_ok=True)
        return copy.deepcopy(value)

    def read(self, revision=None):
        with self.transaction():
            revision = revision or strict_loads(self.head.read_bytes())["revision"]
            if not isinstance(revision, str) or not re.fullmatch("[a-f0-9]{64}", revision):
                raise ValueError("INVALID_REVISION")
            value = strict_loads((self.directory / (revision + ".json")).read_bytes())
            if digest({"files": value["files"], "ledger": value["ledger"]}) != revision:
                raise ValueError("REVISION_CORRUPT")
            return value

    def archive(self, revision, record):
        """Persist observations for export; archives never authorize a future deployment."""
        with self.transaction():
            snapshot = self.read(revision)
            if not isinstance(record, dict) or len(json.dumps(record).encode()) > self.limits["max_source_bytes"]:
                raise ValueError("INVALID_ARCHIVE")
            value = {"archive_version": "1.0", "revision": revision, "record": record,
                     "files": artifact_files(snapshot["files"])}
            archive_id = digest(value)
            path = self.directory / ("archive-" + archive_id + ".json")
            if path.exists():
                return {"archive_id": archive_id}
            if len(list(self.directory.glob("archive-*.json"))) >= self.limits["max_archives"]:
                raise ValueError("ARCHIVE_LIMIT: export records before choosing a new store")
            with path.open("xb") as f:
                f.write(json.dumps(value, ensure_ascii=True, indent=2).encode())
                f.flush()
                os.fsync(f.fileno())
            return {"archive_id": archive_id}

    def archives(self):
        with self.transaction():
            return [strict_loads(p.read_bytes()) for p in sorted(self.directory.glob("archive-*.json"))]

    def edit(self, expected_revision, changes):
        with self.transaction():
            current = self.read()
            if current["revision"] != expected_revision:
                raise ValueError("REVISION_CONFLICT: reload or export your unsaved draft")
            files = dict(current["files"])
            for path, source in changes.items():
                if source is None:
                    if path not in files:
                        raise ValueError("FILE_NOT_FOUND")
                    del files[path]
                else:
                    files[path] = source
            validate_files(files, self.limits)
            return self._write(files, current["ledger"])

    def plan(self, template_id, version, files, expected_revision, metadata=None):
        validate_files(files, self.limits)
        with self.transaction():
            current = self.read()
            if current["revision"] != expected_revision:
                raise ValueError("REVISION_CONFLICT")
            key = template_id + "@" + version
            previous = current["ledger"].get(template_id, {})
            entries = [{"path": path, "base": previous.get("files", {}).get(path),
                        "current": current["files"].get(path), "incoming": source,
                        "action": "conflict" if path in current["files"] else "create",
                        "sha256": hashlib.sha256(source.encode()).hexdigest()}
                       for path, source in sorted(files.items())]
            plan = {"plan_id": uuid.uuid4().hex, "template_id": template_id,
                    "template_version": version, "base_revision": expected_revision,
                    "already_applied": previous.get("version") == version and previous.get("digest") == digest(files),
                    "entries": entries, "key": key, "metadata": copy.deepcopy(metadata or {}),
                    "migration_from": previous.get("version")}
            if len(self.plans) >= self.limits["max_plans"]:
                self.plans.pop(next(iter(self.plans)))
            self.plans[plan["plan_id"]] = plan
            return copy.deepcopy(plan)

    def apply(self, plan_id, expected_revision, resolutions):
        with self.transaction():
            plan = self.plans.get(plan_id)
            current = self.read()
            if plan is None or plan["base_revision"] != expected_revision or current["revision"] != expected_revision:
                raise ValueError("REVISION_CONFLICT")
            files = dict(current["files"])
            if not isinstance(resolutions, dict) or set(resolutions) - {e["path"] for e in plan["entries"]}:
                raise ValueError("INVALID_RESOLUTION")
            if plan["already_applied"] and all(choice == "keep" for choice in resolutions.values()) and all(e["action"] == "conflict" for e in plan["entries"]):
                del self.plans[plan_id]
                return current
            for entry in plan["entries"]:
                path = entry["path"]
                choice = resolutions.get(path, "keep")
                if choice not in ("keep", "incoming"):
                    raise ValueError("INVALID_RESOLUTION")
                if entry["action"] == "create" or choice == "incoming":
                    files[path] = entry["incoming"]
            validate_files(files, self.limits)
            ledger = copy.deepcopy(current["ledger"])
            incoming = {e["path"]: e["incoming"] for e in plan["entries"]}
            ledger[plan["template_id"]] = {"version": plan["template_version"], "digest": digest(incoming),
                                         "files": incoming, "metadata": plan["metadata"], "generated_from_revision": expected_revision}
            result = self._write(files, ledger)
            del self.plans[plan_id]
            return result
