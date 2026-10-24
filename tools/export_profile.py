#!/usr/bin/env python3
"""Generate the Rust/Node test profile from the single editable YAML configuration."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(), offline=args.offline)
    sys.path.insert(0, str(ROOT / "host"))
    from tankbot_host.configuration import load_yaml
    path = ROOT / "core/tests/fixtures/default-profile.json"
    data = json.dumps(load_yaml(ROOT / "config/game.yaml"), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != data:
            raise SystemExit("Generated profile is stale; run python3 tools/export_profile.py")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()
