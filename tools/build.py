#!/usr/bin/env python3
"""Build the Rust core and the locked web editor with one command."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


class BuildError(Exception):
    """A missing tool or incomplete build with an actionable explanation."""


def run(command, root, env):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=root, env=env, check=True)


def node_tools(root, env):
    node = shutil.which("node", path=env.get("PATH"))
    npm = shutil.which("npm", path=env.get("PATH"))
    if not node or not npm:
        raise BuildError("构建编辑器需要 Node.js 22+ 和 npm；安装后重新运行 tools/build.py，或仅构建核心时使用 --core-only。")
    try:
        result = subprocess.run(
            [node, "-p", "JSON.stringify({version:process.versions.node,platform:process.platform,arch:process.arch})"],
            cwd=root, env=env, check=True, capture_output=True, text=True,
        )
        platform = json.loads(result.stdout)
        if int(platform["version"].split(".")[0]) < 22:
            raise BuildError(f"编辑器需要 Node.js 22+，当前为 {platform['version']}。")
        return npm, platform
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        raise BuildError(f"无法检查 Node.js 版本或平台：{exc}") from exc


def supported(values, current):
    if not values:
        return True
    return current not in (item[1:] for item in values if item.startswith("!")) and (
        not any(not item.startswith("!") for item in values) or current in values
    )


def dependencies_ready(root, platform):
    """Check the complete locked tree, including this platform's optional esbuild binary."""
    try:
        manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
        packages = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))["packages"]
        locked_root = packages[""]
        for field in ("dependencies", "devDependencies", "optionalDependencies"):
            if manifest.get(field, {}) != locked_root.get(field, {}):
                raise BuildError(f"package.json 与 package-lock.json 的 {field} 不一致；请维护者更新锁文件。")
        for relative, expected in packages.items():
            if not relative or expected.get("link"):
                continue
            if expected.get("optional") and not (
                supported(expected.get("os"), platform["platform"])
                and supported(expected.get("cpu"), platform["arch"])
            ):
                continue
            try:
                installed = json.loads((root / relative / "package.json").read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                return False
            if installed.get("version") != expected.get("version"):
                return False
            if relative.startswith("node_modules/@esbuild/"):
                binary_dir = root / relative / "bin"
                if not binary_dir.is_dir() or not any(path.is_file() and path.name.startswith("esbuild") for path in binary_dir.iterdir()):
                    return False
        return True
    except FileNotFoundError:
        return False
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BuildError(f"npm manifest 或锁文件无效：{exc}") from exc


def build_editor(root, env, offline):
    npm, platform = node_tools(root, env)
    if not (root / "package-lock.json").is_file():
        raise BuildError("缺少 package-lock.json，无法复现编辑器依赖。")
    if dependencies_ready(root, platform):
        print("已安装的 npm 依赖与锁文件匹配，直接构建编辑器。", flush=True)
    else:
        print("安装锁定的编辑器依赖…", flush=True)
        command = [npm, "ci", "--ignore-scripts", "--include=dev", "--include=optional", "--no-audit", "--no-fund"]
        if offline:
            command.append("--offline")
        try:
            run(command, root, env)
        except subprocess.CalledProcessError as exc:
            hint = "（离线缓存不足；联网构建一次后再尝试 --offline）" if offline else ""
            raise BuildError(f"npm 依赖安装失败{hint}；退出码 {exc.returncode}。") from exc
    try:
        run([npm, "run", "build"], root, env)
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"编辑器构建失败；退出码 {exc.returncode}。") from exc
    for relative in ("build/web/editor-bundle.js", "build/web/THIRD_PARTY_NOTICES.txt"):
        output = root / relative
        if not output.is_file() or output.stat().st_size == 0:
            raise BuildError(f"编辑器构建缺少产物：{relative}。")


def build_core(root, env, args):
    cargo = shutil.which("cargo", path=env.get("PATH"))
    if cargo is None:
        directory = root / ".tools/rust/bin"
        cargo = str(directory / "cargo")
        if not Path(cargo).is_file():
            raise BuildError("需要 Rust 1.99.1；使用 --wasm 时还需要 wasm32-unknown-unknown target。")
        env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")
        env["CARGO_HOME"] = str(root / ".tools/cargo")
    command = [cargo, "fmt", "--all", "--check"] if args.format_check else [cargo, "build", "--locked"]
    if not args.format_check:
        if args.release:
            command.append("--release")
        if args.offline:
            command.append("--offline")
        if args.wasm:
            command.extend(["--target", "wasm32-unknown-unknown", "--lib"])
    try:
        run(command, root, env)
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"Rust 构建或格式检查失败；退出码 {exc.returncode}。") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wasm", action="store_true", help="Build the WASM library probe")
    parser.add_argument("--offline", action="store_true", help="Do not access registries")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--format-check", action="store_true", help="Check Rust formatting only")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--web-only", action="store_true", help="Install/build only the web editor")
    scope.add_argument("--core-only", action="store_true", help="Build only the Rust core")
    args = parser.parse_args(argv)
    if args.web_only and (args.wasm or args.release or args.format_check):
        parser.error("--web-only 不能与 --wasm、--release 或 --format-check 合用")
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    try:
        if not args.core_only and not args.format_check:
            # Fail early when Node is missing, before a potentially long Cargo build.
            node_tools(root, env)
        if not args.web_only:
            build_core(root, env, args)
        if not args.core_only and not args.format_check:
            build_editor(root, env, args.offline)
    except BuildError as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
