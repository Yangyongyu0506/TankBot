import argparse
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def make_parser():
    parser = argparse.ArgumentParser(description="TankBot trusted-local simulation and teaching levels")
    parser.add_argument("mode", choices=("serve", "browser", "headless", "probe"))
    parser.add_argument("--config", type=Path, default=ROOT / "config/game.yaml")
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
    parser.add_argument("--offline", action="store_true", help="Prepare Python dependencies only from the local cache")
    parser.add_argument("--settings-file", type=Path, help="Persistent YAML settings (default: userdata/settings.yaml)")
    parser.add_argument("--save-file", type=Path, help="Campaign save (default: userdata/progress.json)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--developer", dest="developer_mode", action="store_true", default=None, help="Enable local developer mode; practice does not award progress")
    modes.add_argument("--player", dest="developer_mode", action="store_false", help="Use saved campaign unlocks and lesson View Policy")
    return parser


def parse_args(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.level and (args.view or args.robot_demo):
        parser.error("--level 不可与 --view 或 --robot-demo 合用")
    return parser, args


def main():
    parser, args = parse_args()
    from .authority import Authority, load_config
    config = load_config(args.config)
    application = None
    if args.mode in ("serve", "browser"):
        from .application import ApplicationState
        try:
            application = ApplicationState(config, args.settings_file, args.save_file)
            if args.developer_mode is not None:
                value = application.public_settings()
                value["settings"]["developer_mode"] = args.developer_mode
                application.update_settings({"revision": value["revision"], "settings": value["settings"]})
            if not application.developer:
                if not application.levels:
                    parser.error("此配置不含教学关卡；请使用 --developer 运行自由试验场，或选择教学配置。")
                if args.view or args.robot_demo:
                    parser.error("真值练习和机器人演示需要开发者模式；请使用 --developer 或在设置中开启。")
                args.level = args.level or application.progress()["current_level"] or application.levels[0]
            if args.level:
                application.select_level(args.level)
        except (ValueError, OSError) as error:
            parser.error(str(error))
    if args.level:
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
            BrowserServer(config, args.workspace, args.workspace_store, application=application).serve()
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
    authority = Authority(config, workspace=args.workspace, binary=args.core_binary, controlled=args.mode=="headless",
                          developer_mode=bool(application and application.developer))
    try:
        if args.mode == "serve":
            from .server import LocalServer
            try:
                LocalServer(authority, args.workspace, args.workspace_store, application=application).serve()
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
