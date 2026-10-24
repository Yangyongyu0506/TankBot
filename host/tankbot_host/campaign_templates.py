"""Bundled teaching scaffolds. Never execute these helpers in a player Runtime."""

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
        if ctx.config["lesson"]["level_id"] == "c2":
            from perception.tracker import Tracker
            self.tracker = Tracker()

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        level: str = ctx.config["lesson"]["level_id"]
        if level == "c0":
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
    """返回 T_map_radar：把雷达坐标变为地图坐标的 SE(3) 元素。

    输入（使用 own_pose.字段名 读取）：
      own_pose.x_m / y_m: float，自身在地图中的位置，单位 m。
      own_pose.yaw_rad: float，车头相对地图 +x 的逆时针角，单位 rad。

    返回：numpy.ndarray，shape=(4,4)，dtype=float64。
    左上 3x3 放旋转 R，右上 3x1 放雷达原点在 map 中的位置 t。
    最后一行固定为 [0,0,0,1]；本关 z=0，只需考虑绕 z 轴旋转。
    三个旋转列是雷达基向量在地图中的方向，平移列是雷达原点。
    游戏会实际执行 point_map = T_map_radar @ point_radar。
    point_radar 是 [x,y,0,1]，你不需要处理检测列表或消息发布。

    自测：自身 (1,3,pi/2)，雷达点 [2,0,0,1] 应变为 [1,5,0,1]。
    F1 /「关卡说明 / 类型」中的矩阵实验可调整位姿并查看每一行乘法。
    """
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
        """输入已经用 C1 的 SE(3) 矩阵转换到地图系，无需处理网络。

        measurements: tuple[TargetEstimate, ...]，不可变的测量列表。
          有回波时 measurements[0] 的 x_m / y_m 是 float，单位 m。
          丢失时为 ()；先检查 if measurements，再访问第一个元素。
        dt: float，距上次算法调用的仿真秒，不是实际等待时间。
        返回：TargetEstimate 表示当前地图目标估计；None 表示尚无估计。
        更新 self.estimate 可保留状态；不要每次调用都把状态清空。
        平滑、窗口或预测等方法均可。F1 可查看类型定义与调用示例。
        """
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


def teaching_sources(level_id: str) -> dict[str, str]:
    files: dict[str, str] = {"campaign_robot.py": WRAPPER}
    if level_id in ("c1", "c2"):
        files.update({"perception/__init__.py": "", "perception/transforms.py": TRANSFORMS,
                      "tests/test_coordinates.py": COORDINATE_TEST})
    if level_id == "c2":
        files["perception/tracker.py"] = TRACKER
    return files
