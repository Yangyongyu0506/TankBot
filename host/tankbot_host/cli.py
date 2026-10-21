import argparse
import json
from pathlib import Path
from .authority import Authority, load_config, ROOT


def main():
    parser = argparse.ArgumentParser(description="TankBot M1 trusted-local prototype")
    parser.add_argument("mode", choices=("serve", "headless", "probe"))
    parser.add_argument("--config", type=Path, default=ROOT / "config/m1.json")
    parser.add_argument("--chassis", choices=("differential", "omnidirectional"))
    parser.add_argument("--core-binary", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--ticks", type=int)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.chassis:
        config["scene"]["default_chassis"] = args.chassis
    if args.mode == "probe":
        from .authority import CoreAdapter
        core = CoreAdapter(config, config["scene"]["default_chassis"], args.core_binary)
        try:
            print(core.call({"op": "probe", "config": config}))
        finally:
            core.close()
        return
    authority = Authority(config, workspace=args.workspace, binary=args.core_binary, controlled=args.mode=="headless")
    try:
        if args.mode == "serve":
            from .server import LocalServer
            try:
                LocalServer(authority).serve()
            except KeyboardInterrupt:
                pass
        else:
            for _ in range(args.ticks if args.ticks is not None else config["validation"]["ticks"]):
                authority.advance()
            print(json.dumps({"tick": authority.tick, "truth_digest": authority.truth_digest(),
                              "pose_commits": sum(e["event"]=="pose_commit" for e in authority.audit),
                              "rejections": [e for e in authority.audit if e["event"]=="rejected"]}, indent=2))
    finally:
        authority.close()
