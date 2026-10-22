#!/usr/bin/env python3
"""Build with a normal Rust install or the optional repository-local development toolchain."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wasm", action="store_true", help="Build the WASM library probe")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--format-check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cargo = shutil.which("cargo")
    env = os.environ.copy()
    if cargo is None:
        directory = root / ".tools/rust/bin"
        cargo = str(directory / "cargo")
        if not Path(cargo).is_file():
            parser.error("Install Rust 1.99.1 and wasm32-unknown-unknown (for --wasm)")
        env["PATH"] = str(directory)+os.pathsep+env.get("PATH", "")
        env["CARGO_HOME"] = str(root / ".tools/cargo")
    command = [cargo, "fmt", "--all", "--check"] if args.format_check else [cargo, "build", "--locked"]
    if not args.format_check:
        if args.release:
            command.append("--release")
        if args.offline:
            command.append("--offline")
        if args.wasm:
            command.extend(["--target", "wasm32-unknown-unknown", "--lib"])
    subprocess.run(command, cwd=root, env=env, check=True)


if __name__ == "__main__":
    main()
