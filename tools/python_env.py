"""Standard-library-only dependency bootstrap; never installs into the caller's Python."""
from contextlib import contextmanager
import hashlib
import errno
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import sysconfig
import time
import urllib.error
import urllib.request
import venv

ROOT = Path(__file__).resolve().parents[1]
PROBE = '''import importlib, importlib.metadata as m, json, sys
request = json.load(sys.stdin)
versions, problems = {}, []
for name, expected in request["requirements"].items():
    try:
        versions[name] = m.version(name)
        if versions[name] != expected:
            problems.append(name + ": " + versions[name] + " (required " + expected + ")")
    except m.PackageNotFoundError:
        problems.append(name + ": missing")
for name in request["imports"]:
    try:
        importlib.import_module(name)
    except Exception as error:
        problems.append(name + ": " + type(error).__name__)
print(json.dumps({"ready": not problems, "versions": versions, "problems": problems,
                  "executable": sys.executable, "prefix": sys.prefix}))
'''


class BootstrapError(Exception):
    """An actionable installation failure, before any game process starts."""


def requirements(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9_.+!-]+)", line)
        if not match:
            raise BootstrapError("requirements.txt 必须使用固定版本 name==version：" + line)
        result[match[1]] = match[2]
    return result


def probe(python, expected, imports):
    try:
        result = subprocess.run([str(python), "-I", "-c", PROBE], input=json.dumps({"requirements": expected, "imports": imports}),
                                text=True, capture_output=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"ready": False, "versions": {}, "problems": ["Python 环境无法加载依赖"]}


def environment_key(root):
    identity = {"root": str(root.resolve()), "python": sys.version, "platform": sys.platform,
                "machine": platform.machine(), "abi": sysconfig.get_config_var("SOABI"),
                "base": str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
                "requirements": (root / "requirements.txt").read_text(encoding="utf-8"),
                "bootstrap": (root / "config/python-bootstrap.lock.json").read_text(encoding="utf-8")}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]


def environment_python(directory):
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


@contextmanager
def installation_lock(path, timeout=300):
    """OS locks release even if installation is interrupted or a process is killed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        deadline = time.monotonic() + timeout
        waiting = False
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN):
                    raise BootstrapError("无法锁定 Python 依赖缓存目录。") from error
                if time.monotonic() >= deadline:
                    raise BootstrapError("等待 Python 依赖安装超时；请稍后重试。")
                if not waiting:
                    print("另一个 TankBot 进程正在准备依赖，等待完成…", flush=True); waiting = True
                time.sleep(.2)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def installer_wheel(cache, lock, offline):
    path = cache / "bootstrap" / lock["filename"]
    def valid():
        return path.is_file() and path.stat().st_size == lock["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == lock["sha256"]
    if valid():
        return path
    if offline:
        raise BootstrapError("离线缓存缺少完整的 Python 安装器；请联网运行同一启动命令一次。")
    path.parent.mkdir(parents=True, exist_ok=True)
    print("准备 Python 安装器…", flush=True)
    temporary = path.with_suffix(".download")
    try:
        with urllib.request.urlopen(lock["url"], timeout=45) as response:
            raw = response.read(lock["bytes"] + 1)
        if len(raw) != lock["bytes"] or hashlib.sha256(raw).hexdigest() != lock["sha256"]:
            raise BootstrapError("Python 安装器下载校验失败；请重新运行启动命令。")
        temporary.write_bytes(raw)
        temporary.replace(path)
    except (OSError, urllib.error.URLError) as error:
        raise BootstrapError("无法下载 Python 安装器；请检查网络或代理后重新运行同一启动命令。") from error
    finally:
        temporary.unlink(missing_ok=True)
    return path


def install(python, cache, root, lock, offline):
    wheel = installer_wheel(cache, lock["pip"], offline)
    # Like ensurepip, run pip from a verified wheel to seed a pip-free venv.
    seed = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('pip',run_name='__main__')"
    common = ["--isolated", "--disable-pip-version-check", "--require-virtualenv", "--cache-dir", str(cache / "pip-cache")]
    commands = [[str(python), "-I", "-c", seed, str(wheel), *common, "install", "--no-index", "--no-deps", str(wheel)]]
    wheels = cache / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    pip = [str(python), "-I", "-m", "pip", *common]
    if not offline:
        commands.append([*pip, "download", "--only-binary=:all:", "--retries", "2", "--timeout", "30",
                         "--dest", str(wheels), "--requirement", str(root / "requirements.txt")])
    commands.append([*pip, "install", "--no-index", "--only-binary=:all:", "--find-links", str(wheels),
                     "--upgrade", "--force-reinstall", "--requirement", str(root / "requirements.txt")])
    # Ignore destination overrides: installers may only write to this venv/cache.
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "PIP_"))}
    env["PIP_CONFIG_FILE"] = os.devnull
    env["PIP_CACHE_DIR"] = str(cache / "pip-cache")
    for command in commands:
        try:
            subprocess.run(command, cwd=root, env=env, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            hint = "离线 wheel 缓存不完整，请联网重试。" if offline else "请检查网络、代理或上方安装错误后重新运行同一启动命令。"
            raise BootstrapError("Python 依赖准备失败。" + hint) from error


def ensure_environment(root=ROOT, *, offline=False):
    """Return the interpreter to relaunch, or None if this Python already works."""
    root = Path(root).resolve()
    if sys.version_info < (3, 11):
        raise BootstrapError("TankBot 需要 Python 3.11 或更高版本。")
    expected = requirements(root / "requirements.txt")
    lock = json.loads((root / "config/python-bootstrap.lock.json").read_text(encoding="utf-8"))
    if probe(sys.executable, expected, lock["import_checks"])["ready"]:
        return None
    cache = root / ".m1-cache/python"
    key = environment_key(root)
    directory = cache / "envs" / key
    python = environment_python(directory)
    # Shared wheel files also need serialization across different requirements keys.
    with installation_lock(cache / "install.lock"):
        status = probe(python, expected, lock["import_checks"])
        if not status["ready"]:
            print("首次运行或依赖需要更新，正在自动准备 TankBot Python 环境…", flush=True)
            if not python.is_file():
                venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(directory)
            install(python, cache, root, lock, offline)
            status = probe(python, expected, lock["import_checks"])
            if not status["ready"]:
                raise BootstrapError("Python 依赖安装后仍无法加载：" + "; ".join(status["problems"]))
            metadata = {"requirements_sha256": hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest(), **status}
            temporary = directory / "ready.json.tmp"
            temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(directory / "ready.json")
            print("Python 依赖已准备好，继续启动游戏。", flush=True)
    return python


def relaunch_if_needed(entry, *, offline=False):
    try:
        python = ensure_environment(offline=offline)
        if python is not None:
            os.execv(str(python), [str(python), "-I", str(entry), *sys.argv[1:]])
    except (BootstrapError, OSError, ValueError) as error:
        print("启动失败：" + str(error), file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
