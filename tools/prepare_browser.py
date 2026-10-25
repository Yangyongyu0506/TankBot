#!/usr/bin/env python3
"""Fetch pinned public Pyodide artifacts; assemble separate trusted/player bundles locally."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "tools"))
DEST = ROOT / "build/browser"
LOCK = ROOT / "config/browser-assets.lock.json"


def bundle(paths):
    return {str(p.relative_to(ROOT)): p.read_text() for p in sorted(set(paths))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--create-lock", action="store_true", help="Maintainer-only intentional dependency update")
    args = parser.parse_args()
    artifacts = DEST / "pyodide"
    artifacts.mkdir(parents=True, exist_ok=True)
    if args.create_lock:
        version = "0.29.5"
        base = f"https://cdn.jsdelivr.net/pyodide/v{version}/full/"
        upstream = json.loads(urllib.request.urlopen(base+"pyodide-lock.json", timeout=45).read())
        names = {"pyodide.js", "pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"}
        def include(name):
            pkg = upstream["packages"][name.replace("_", "-")]
            names.add(pkg["file_name"])
            for dep in pkg["depends"]:
                include(dep)
        include("jsonschema")
        include("numpy")
        def fetch(name):
            raw = urllib.request.urlopen(base+name, timeout=90).read()
            (artifacts/name).write_bytes(raw)
            return name, {"sha256": hashlib.sha256(raw).hexdigest(), "bytes":len(raw)}
        with ThreadPoolExecutor(max_workers=4) as pool:
            files = dict(pool.map(fetch, sorted(names)))
        for package in upstream["packages"].values():
            if package["file_name"] in files and package["sha256"] != files[package["file_name"]]["sha256"]:
                raise SystemExit("Upstream package hash mismatch")
        LOCK.write_text(json.dumps({"version":version,"base_url":base,"files":files},indent=2)+"\n")
    lock = json.loads(LOCK.read_text())
    def verify(item):
        name, meta = item
        path = artifacts/name
        if not path.exists():
            if args.offline:
                raise SystemExit(f"Missing {path}; run tools/prepare_browser.py online once")
            path.write_bytes(urllib.request.urlopen(lock["base_url"]+name, timeout=90).read())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta["sha256"]:
            raise SystemExit(f"Hash mismatch: {path}; remove damaged cache and retry")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(verify, lock["files"].items()))
    common = list((ROOT/"protocol/tankbot_protocol").glob("*.py"))
    common = [p for p in common if p.name in ("__init__.py","message.py","wire.py")]
    common += list((ROOT/"sdk/python/tankbot").glob("*.py")) + [ROOT/"runtime/module_runner.py", ROOT/"runtime/graph_runner.py", ROOT/"runtime/source_loader.py"]
    # Player bundle contains SDK/runner only. Workspace sources are a separate deployment snapshot.
    (DEST/"player-bundle.json").write_text(json.dumps(bundle(common)))
    trusted = common + list((ROOT/"host/tankbot_host").glob("*.py"))
    trusted += list((ROOT/"protocol/tankbot_protocol").glob("*.py")) + [ROOT/"runtime/browser_authority.py"]
    trusted += list((ROOT/"docs/schemas").glob("*.schema.json"))
    trusted += list((ROOT/"docs/examples").glob("*.json"))
    trusted += [ROOT/"requirements.txt", ROOT/"config/browser-assets.lock.json", ROOT/"config/player-dependencies.yaml", ROOT/"config/game.yaml"]
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(), offline=args.offline)
    import sys
    sys.path.insert(0, str(ROOT / "host"))
    from tankbot_host.configuration import load_yaml
    trusted_bundle = bundle(trusted)
    trusted_bundle["config/player-dependencies.json"] = json.dumps(load_yaml(ROOT/"config/player-dependencies.yaml"))
    (DEST/"authority-bundle.json").write_text(json.dumps(trusted_bundle))
    print(f"Browser bundles ready; pinned Pyodide {lock['version']}, {sum(f['bytes'] for f in lock['files'].values())} artifact bytes")


if __name__ == "__main__":
    main()
