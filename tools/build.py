#!/usr/bin/env python3
"""Build the authoritative Rust Core; Godot is prepared by the game launcher."""

import argparse
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


def cargo_tool(root, env):
    """Reuse the same normal/local toolchain selection for builds and regression checks."""
    cargo = shutil.which("cargo", path=env.get("PATH"))
    if cargo is None:
        directory = root / ".tools/rust/bin"
        cargo = str(directory / "cargo")
        if not Path(cargo).is_file():
            raise BuildError("需要 Rust 1.99.1；使用 --wasm 时还需要 wasm32-unknown-unknown target。")
        env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")
        env["CARGO_HOME"] = str(root / ".tools/cargo")
    return cargo


def build_core(root, env, args):
    if not args.format_check:
        export = [sys.executable, str(root / "tools/export_profile.py")]
        if args.offline:
            export.append("--offline")
        try:
            run(export, root, env)
        except subprocess.CalledProcessError as exc:
            raise BuildError("无法从 config/game.yaml 生成核心测试配置。") from exc
    cargo = cargo_tool(root, env)
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
    parser.add_argument("--wasm", action="store_true", help="Build the standalone WASM Core (no browser GUI)")
    parser.add_argument("--offline", action="store_true", help="Do not access registries")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--format-check", action="store_true", help="Check Rust formatting only")
    parser.add_argument("--core-only", action="store_true", help=argparse.SUPPRESS)  # Native build compatibility alias.
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    try:
        build_core(root, env, args)
    except BuildError as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
