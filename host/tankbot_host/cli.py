import argparse
import json
from pathlib import Path
from .authority import Authority, load_config, ROOT


def main():
    parser = argparse.ArgumentParser(description="TankBot trusted-local simulation and teaching levels")
    parser.add_argument("mode", choices=("serve", "browser", "headless", "probe"))
    parser.add_argument("--config", type=Path, default=ROOT / "config/m1.json")
    parser.add_argument("--level", choices=("c0", "c1", "c2"), help="Start a teaching level with its authorized capabilities")
    parser.add_argument("--chassis", choices=("differential", "omnidirectional"))
    parser.add_argument("--core-binary", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--workspace-store", type=Path, help="Persistent versioned editor store; --workspace remains a read-only seed")
    parser.add_argument("--ticks", type=int)
    parser.add_argument("--view", choices=("estimated", "weapons-practice"))
    parser.add_argument("--robot-demo", action="store_true", help="Run the separate SDK turret/fire example")
    parser.add_argument("--fault", choices=("none","infinite_loop","exception","bad_covariance","no_output"), help="Local failure probe")
    parser.add_argument("--browser-qa", action="store_true", help="Run explicit M2 browser security/fixture probes")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.level:
        if args.view or args.robot_demo:
            parser.error("--level 不可与 --view 或 --robot-demo 合用")
        from .campaign import configure
        config = configure(config, args.level)
    if args.chassis:
        config["scene"]["default_chassis"] = args.chassis
    if args.view:
        config["view_mode"] = args.view
        if args.view == "weapons-practice":
            config["view_policy"] = config["practice_view_policy"]
    if args.robot_demo:
        config["control_sources"].update(turret="robot", weapon="robot")
        config["module"]["entry_point"] = "weapon_demo:WeaponDemo"
        config["module"]["weapon_demo"]["enabled"] = True
    if args.fault:
        config["module"]["fault"] = args.fault
    if args.browser_qa:
        config["browser"]["probe_enabled"] = True
    if args.mode == "browser":
        from .browser_server import BrowserServer
        try:
            BrowserServer(config, args.workspace, args.workspace_store).serve()
        except KeyboardInterrupt:
            pass
        return
    if args.mode == "probe":
        from .authority import CoreAdapter
        core = CoreAdapter(config, config["scene"]["default_chassis"], args.core_binary)
        try:
            print(core.call({"op": "probe", "config": config}))
        finally:
            core.close()
        return
    if config.get("campaign", {}).get("active_level"):
        from .campaign import ensure_native_numpy
        try:
            ensure_native_numpy()
        except ValueError as error:
            parser.error(str(error))
    authority = Authority(config, workspace=args.workspace, binary=args.core_binary, controlled=args.mode=="headless")
    try:
        if args.mode == "serve":
            from .server import LocalServer
            try:
                LocalServer(authority, args.workspace, args.workspace_store).serve()
            except KeyboardInterrupt:
                pass
        else:
            for _ in range(args.ticks if args.ticks is not None else config["validation"]["ticks"]):
                authority.advance()
            print(json.dumps({"tick": authority.tick, "truth_digest": authority.truth_digest(),
                              "pose_commits": sum(e["event"]=="pose_commit" for e in authority.audit),
                              "rejections": [e for e in authority.audit if e["event"]=="rejected"],
                              "campaign": authority.campaign_status()}, indent=2))
    finally:
        authority.close()
