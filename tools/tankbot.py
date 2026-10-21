#!/usr/bin/env python3
"""Repository entry point; requires no package installation for project modules."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "host"), str(ROOT / "protocol"), str(ROOT / "sdk/python")]
from tankbot_host.cli import main
if __name__ == "__main__":
    main()
