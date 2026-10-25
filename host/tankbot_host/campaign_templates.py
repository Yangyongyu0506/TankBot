"""Bundled teaching scaffolds. Never execute these helpers in a player Runtime."""
import ast
import json
import re

TEMPLATE_VERSION: str = "1.2.0"

WRAPPER: str = '''# TankBot managed scaffold 1.2.0 — 算法只需填写 perception/ 中的 TODO。
from __future__ import annotations
from typing import TYPE_CHECKING, cast
import numpy as np
from numpy.typing import NDArray
from tankbot import Inputs, Module, ModuleContext, Pose2D, RadarData, RadarDetection, Sample, TargetEstimate
from tankbot.transforms import radar_point, validate_se3

if TYPE_CHECKING:
    from perception.tracker import Tracker


class CampaignRobot(Module):
    def setup(self, ctx: ModuleContext) -> None:
        self.tracker: Tracker | None = None
        self.last_sample: int | None = None
        if ctx.config["lesson"]["processing"] == "track":
            from perception.tracker import Tracker
            self.tracker = Tracker()

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        processing: str = ctx.config["lesson"]["processing"]
        if processing == "passive":
            return
        pose: Sample[Pose2D] | None = cast("Sample[Pose2D] | None", inputs.latest("self_pose"))
        radar: Sample[RadarData] | None = cast("Sample[RadarData] | None", inputs.latest("radar"))
        if pose is None or radar is None or radar.simulation_tick == self.last_sample:
            return
        self.last_sample = radar.simulation_tick
        from perception.transforms import radar_to_map
        try:
            transform: NDArray[np.float64] = validate_se3(radar_to_map(pose.data), tolerance=ctx.config["lesson"]["transform_tolerance"])
        except NotImplementedError:
            return  # 等待玩家完成矩阵函数；正式测试会给出具体 TODO 提示。
        points_list: list[TargetEstimate] = []
        hit: RadarDetection
        for hit in radar.data.detections:
            point_radar: NDArray[np.float64] = radar_point(hit)
            point_map: NDArray[np.float64] = transform @ point_radar
            point: TargetEstimate = TargetEstimate(x_m=float(point_map[0]), y_m=float(point_map[1]))
            points_list.append(point)
        points: tuple[TargetEstimate, ...] = tuple(points_list)
        estimate: TargetEstimate | None = (points[0] if points else None) if self.tracker is None else self.tracker.update(points, ctx.dt_seconds)
        if estimate is not None:
            ctx.publish("target", estimate, frame_id="map", simulation_tick=radar.simulation_tick)
'''

TRANSFORMS: str = '''import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D
import math


def radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:
    """Algorithm input/output contract; see level guidance."""
    T_map_radar: NDArray[np.float64] = np.eye(4, dtype=np.float64)
    # TODO: 填写旋转和位移。完成后把下一行替换成 return T_map_radar。
    raise NotImplementedError("请完成 perception/transforms.py 中的 SE(3) 矩阵")
'''

TRACKER: str = '''from tankbot import TargetEstimate


class Tracker:
    def __init__(self) -> None:
        # self.estimate 在 update 调用之间保留，部署或重试时重新初始化。
        self.estimate: TargetEstimate | None = None

    def update(self, measurements: tuple[TargetEstimate, ...], dt: float) -> TargetEstimate | None:
        """Algorithm input/output contract; see level guidance."""
        # TODO: 减少抖动，并为没有测量的时刻保留合理的状态。
        return self.estimate
'''

COORDINATE_TEST: str = '''import math
import unittest
import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D
from tankbot.transforms import validate_se3
from perception.transforms import radar_to_map


class CoordinateTest(unittest.TestCase):
    def test_rotated_robot(self) -> None:
        matrix: NDArray[np.float64] = validate_se3(radar_to_map(Pose2D(1.0, 3.0, math.pi/2)), tolerance=1e-8)
        point: NDArray[np.float64] = matrix @ np.array([2.0, 0.0, 0.0, 1.0])
        np.testing.assert_allclose(point, [1.0, 5.0, 0.0, 1.0], atol=1e-8)

    def test_translation_and_direction(self) -> None:
        matrix: NDArray[np.float64] = validate_se3(radar_to_map(Pose2D(2.0, -1.0, 0.0)), tolerance=1e-8)
        np.testing.assert_allclose(matrix @ np.array([1.0, 2.0, 0.0, 1.0]), [3.0, 1.0, 0.0, 1.0])
        np.testing.assert_allclose(matrix @ np.array([1.0, 2.0, 0.0, 0.0]), [1.0, 2.0, 0.0, 0.0])
'''


MANAGED_FILES: tuple[str, ...] = ("campaign_robot.py", "tankbot.json", "contracts/perception.json", "tests/test_coordinates.py")


def template_version(config: dict) -> str:
    level = config.get("campaign", {}).get("active_level")
    return config["campaign"]["levels"][level]["runtime"]["template_version"] if level else TEMPLATE_VERSION


def framework_upgrade(config: dict, files: dict[str, str]) -> dict:
    """One compatibility check for the editor and Test; comments are not an API."""
    level = config.get("campaign",{}).get("active_level")
    profile_name = config["campaign"]["levels"][level].get("robot_profile") if level else None
    if profile_name:
        profile = config["robot_graph"]["profiles"][profile_name]
        try:
            manifest = json.loads(files.get("tankbot.json","{}"))
            current = len(manifest.get("modules",[])) > 1 and all(item["contract"] in files for item in manifest["modules"])
            if current and manifest.get("project_id") == profile["manifest"]["project_id"]:
                # C3 -> C4 changes the tracked value from XY to XY/yaw. Existing
                # multi-module scaffolding is not necessarily this lesson's scaffold.
                for item in manifest["modules"]:
                    expected = profile["contracts"].get(item["module_id"])
                    if expected and item["contract"] == f"contracts/{item['module_id']}.json":
                        contract = json.loads(files[item["contract"]])
                        current &= all({p:v["schema"] for p,v in contract[field].items()} ==
                                       {p:v["schema"] for p,v in expected[field].items()} for field in ("inputs","outputs"))
        except (ValueError,KeyError,TypeError):
            current = False
        return {"required":not current,"current_version":None,"target_version":profile["template_version"],
                "managed_files":profile["managed_files"],"message":"本关使用多模块框架；请预览升级，已有 perception/ 和 weapons/ 算法文件会保留。" if not current else ""}
    source: str = files.get("campaign_robot.py", "")
    marker: re.Match | None = re.search(r"^\s*# TankBot managed scaffold ([0-9.]+)(?:\s|$)", source, re.MULTILINE)
    current: bool = marker is not None and marker.group(1) == TEMPLATE_VERSION
    if not current:
        try:
            # A deleted version comment or formatting-only edit must not block valid code.
            current = ast.dump(ast.parse(source)) == ast.dump(ast.parse(WRAPPER))
        except SyntaxError:
            current = True  # Let Test report the syntax error before classifying framework compatibility.
    manifest_mismatch = False
    if level and "tankbot.json" in files:
        try:
            manifest = json.loads(files["tankbot.json"])
            modules = manifest.get("modules")
            expected = config["campaign"]["levels"][level]["runtime"]["manifest"]["modules"]
            # A compatible wrapper can survive a later lesson's graph upgrade.
            # Check the active declaration too, without rewriting any player files.
            if isinstance(modules,list) and modules and all(isinstance(item,dict) and isinstance(item.get("module_id"),str) for item in modules):
                manifest_mismatch = len(modules)!=1 or modules[0]["module_id"]!=expected[0]["module_id"]
                current &= not manifest_mismatch
        except (ValueError,AttributeError,TypeError):
            pass  # Invalid manifests still belong to the ordinary Schema validator.
    required: bool = bool(config.get("campaign", {}).get("active_level") and not current)
    return {"required": required, "current_version": marker.group(1) if marker else None,
            "target_version": TEMPLATE_VERSION, "managed_files": config["campaign"]["levels"][level]["runtime"]["managed_files"] if level else list(MANAGED_FILES),
            "message": ("当前工作区的模块配置与本关不匹配；本关使用单模块框架。请预览并切换本关运行配置，已有算法文件和历史版本会保留。"
                        if manifest_mismatch else "当前项目的课程运行框架需要更新，算法尚未开始测试。预览后可保留算法文件，更新框架并继续测试。") if required else ""}
