"""Shared educational import policy, not a security sandbox for hostile Python."""
import ast
import builtins
import copy
import importlib.abc
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys


class DependencyNotAllowed(ImportError):
    pass


def load_policy():
    directory = Path(__file__).resolve().parents[3] / "config"
    compiled = directory / "player-dependencies.json"
    if compiled.exists():
        value = json.loads(compiled.read_text(encoding="utf-8"))
    else:
        import yaml
        value = yaml.safe_load((directory / "player-dependencies.yaml").read_text(encoding="utf-8"))
    fields = {"policy_version", "external_packages", "standard_modules", "test_modules", "sdk_modules"}
    if (not isinstance(value, dict) or set(value) != fields or type(value["policy_version"]) is not int or value["policy_version"] != 1
            or any(not isinstance(value[key], list) or not value[key] or any(not isinstance(name, str) for name in value[key])
                   or len(set(value[key])) != len(value[key]) for key in fields - {"policy_version"})):
        raise ValueError("INVALID_PLAYER_IMPORT_POLICY")
    return value


def local_roots(files):
    return {path.split("/")[0].removesuffix(".py") for path in files if path.endswith(".py")}


def check_import(name, policy, local, *, tests=False, fromlist=()):
    root = name.split(".", 1)[0]
    standard = policy["standard_modules"] + (policy["test_modules"] if tests else [])
    if root == "tankbot":
        if name not in policy["sdk_modules"] or any(item.startswith("_") for item in fromlist):
            raise DependencyNotAllowed("DEPENDENCY_NOT_ALLOWED: " + name)
        return
    if root not in {*standard, *policy["external_packages"], *local}:
        raise DependencyNotAllowed("DEPENDENCY_NOT_ALLOWED: " + name + "；仅开放 NumPy、SDK 和指定基础标准库，请查看关卡说明。")


def validate_imports(files, policy):
    local = local_roots(files)
    reserved = set(sys.stdlib_module_names) | {"tankbot", "tankbot_protocol", "module_runner", "source_loader", "js", "pyodide", *policy["external_packages"]}
    for path, source in files.items():
        if not path.endswith(".py"):
            continue
        if path.split("/")[0].removesuffix(".py") in reserved:
            raise ValueError("RESERVED_MODULE: " + path)
        package = path.rsplit("/", 1)[0].replace("/", ".") if "/" in path else ""
        tree = ast.parse(source, filename=path)
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [(item.name, ()) for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                try:
                    name = importlib.util.resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
                except (ImportError, ValueError) as error:
                    raise ValueError(f"{path}:{node.lineno}:1: INVALID_RELATIVE_IMPORT") from error
                imports = [(name, tuple(item.name for item in node.names))]
            for name, fromlist in imports:
                try:
                    check_import(name, policy, local, tests=path.startswith("tests/"), fromlist=fromlist)
                except DependencyNotAllowed as error:
                    raise ValueError(f"{path}:{node.lineno}:1: {error}") from error


class WorkspaceLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, guard):
        super().__init__(name, str(path))
        self.guard = guard

    def exec_module(self, module):
        relative = Path(self.path).relative_to(self.guard.root).as_posix()
        source = Path(self.path).read_text(encoding="utf-8")
        validate_imports({**self.guard.sources, relative: source}, self.guard.policy)
        original = builtins.__import__
        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            full = importlib.util.resolve_name("." * level + name, (globals or {}).get("__package__", "")) if level else name
            check_import(full, self.guard.policy, self.guard.local, tests=relative.startswith("tests/"), fromlist=fromlist)
            return original(name, globals, locals, fromlist, level)
        module.__builtins__ = {**vars(builtins), "__import__": guarded_import}
        exec(compile(source, self.path, "exec"), module.__dict__)


class WorkspaceImports(importlib.abc.MetaPathFinder):
    def __init__(self, root, sources, policy):
        self.root = Path(root).resolve()
        self.sources = copy.deepcopy(sources)
        self.local = local_roots(sources)
        self.policy = copy.deepcopy(policy)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] not in self.local:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path if path is not None else [str(self.root)])
        if spec is None:
            raise ModuleNotFoundError("No workspace module named " + fullname)
        if spec.origin is None:
            if any(not Path(p).resolve().is_relative_to(self.root) for p in spec.submodule_search_locations or []):
                raise DependencyNotAllowed("DEPENDENCY_NOT_ALLOWED: " + fullname)
        elif not Path(spec.origin).resolve().is_relative_to(self.root):
            raise DependencyNotAllowed("DEPENDENCY_NOT_ALLOWED: " + fullname)
        else:
            spec.loader = WorkspaceLoader(fullname, spec.origin, self)
        return spec


def install_workspace_imports(root, policy):
    root = Path(root).resolve()
    sources = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.py")
               if "__pycache__" not in p.parts and not any(part.startswith(".") for part in p.relative_to(root).parts)}
    validate_imports(sources, policy)
    guard = WorkspaceImports(root, sources, policy)
    for name in guard.local:
        existing = sys.modules.get(name)
        if existing is not None and not Path(getattr(existing, "__file__", "") or "/").resolve().is_relative_to(root):
            raise DependencyNotAllowed("DEPENDENCY_NOT_ALLOWED: workspace module conflicts with loaded package " + name)
    sys.meta_path.insert(0, guard)
    return guard
