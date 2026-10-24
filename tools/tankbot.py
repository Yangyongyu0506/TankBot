#!/usr/bin/env python3
"""Repository entry point; automatically prepares missing Python dependencies."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ("host", "protocol", "sdk/python", "tools")]
if __name__ == "__main__":
    from tankbot_host.cli import parse_args
    _, options = parse_args()  # --help / invalid arguments never install packages.
    from python_env import relaunch_if_needed
    relaunch_if_needed(Path(__file__).resolve(), offline=options.offline)
    from tankbot_host.cli import main
    main()
