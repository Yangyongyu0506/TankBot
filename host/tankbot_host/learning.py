"""Player-facing explanations from trusted lesson text and actual SDK type declarations."""
import ast
import copy
from dataclasses import MISSING, fields, is_dataclass
import inspect
from functools import lru_cache
from typing import Any, get_type_hints
import tankbot
from .campaign_templates import TEMPLATE_VERSION, TRANSFORMS, TRACKER


TYPE_TEXT: dict[str, tuple[str, dict[str, str]]] = {
    "Pose2D": ("自身的二维位姿。C0–C2 由系统公开提供；位置在 map 中，车头方向用 yaw 表示。", {
        "x_m": "地图横坐标，单位 m，向右为正。", "y_m": "地图纵坐标，单位 m，向上为正。",
        "yaw_rad": "车头相对地图 +x 的逆时针角，单位 rad；π/2 表示朝向 +y。",
        "covariance": "可空的行优先 3×3 协方差，依次对应 x、y、yaw；本关可以忽略。",
        "child_frame_id": "被描述的车体系名称，通常为 base_link；本关可以忽略。"}),
    "RadarDetection": ("一次雷达检测。先在车体系里测量，不能直接当作地图坐标。", {
        "observation_id": "仅本次观测的标签；不能用它识别跨帧的同一敌车。",
        "range_m": "传感器中心到目标中心的距离，单位 m。",
        "bearing_rad": "相对车头的方位角，单位 rad；前方为 0，左侧为正。"}),
    "RadarData": ("一帧雷达数据。没有检测时 detections 是空元组 ()。", {"detections": "不可变的 RadarDetection 元组；逐项读取，不需要解析 JSON。"}),
    "TargetEstimate": ("算法在 map 中估计的目标位置。C2 跟踪器返回这个值；C1 的矩阵结果由框架转换为它。", {
        "x_m": "目标估计的地图横坐标，单位 m。", "y_m": "目标估计的地图纵坐标，单位 m。",
        "covariance": "可空的行优先 2×2 协方差，对应 x、y；入门时保留 None。"}),
    "Sample": ("框架使用的带采样时刻的数据包装；入门函数收到的是内部 data，无需手动拆包。", {
        "data": "类型参数 T 对应的数据，例如 Pose2D 或 RadarData。", "simulation_tick": "数据采样的仿真 tick，不是网络到达时间。",
        "frame_id": "数据参考坐标系名称。", "sequence_number": "该数据流递增的序号。"}),
    "JointState": ("按轮名排列的关节角、角速度和力矩，主要用于后续里程计。", {
        "name": "轮/关节名称元组。", "position": "与 name 对齐的累计角，单位 rad。",
        "velocity": "与 name 对齐的角速度，单位 rad/s。", "effort": "力矩，单位 N·m；未报告时为空元组。"}),
    "ImuData": ("车体系内的惯性观测。", {"angular_velocity_z_radps": "绕 z 的角速度，rad/s。",
        "linear_acceleration_x_mps2": "沿车头 x 的加速度，m/s²。", "linear_acceleration_y_mps2": "沿车体左方 y 的加速度，m/s²。"}),
    "EncoderData": ("累计轮距的旧示例类型；当前轮组观测使用 JointState。", {
        "left_distance_m": "本 run 起的左轮累计距离，m。", "right_distance_m": "本 run 起的右轮累计距离，m。"}),
    "Vector3": ("三维向量；具体单位由使用它的接口决定。", {"x": "x 分量。", "y": "y 分量。", "z": "z 分量。"}),
    "Twist": ("车体系目标速度。二维模型只使用 linear.x/y 和 angular.z。", {
        "linear": "线速度，m/s。", "angular": "角速度，rad/s。"}),
    "TurretVelocity": ("炮台相对车体的目标角速度。", {"velocity_radps": "逆时针为正，单位 rad/s。"}),
    "FireCommand": ("一次单发开火意图，进阶接口由 ModuleContext.fire 生成幂等请求。", {}),
    "FireResult": ("自己提交的开火请求结果；不含命中坐标。", {"request_id": "请求标识。", "status": "fired/cooldown/blocked/resource_limit。", "processed_tick": "处理请求的仿真 tick。"}),
    "WeaponState": ("自己的武器状态。", {"ready": "是否可以开火。", "cooldown_remaining_ticks": "剩余冷却 tick。",
        "shots_fired": "本 run 已发射数量。", "hits_received": "自己的受击计数。", "last_result": "最近一次开火结果，无结果时为 None。"}),
    "Inputs": ("框架端口输入集合；入门关卡已替你取出具体数据。", {}),
    "ModuleContext": ("框架提供的时间、只读配置和输出接口。", {"simulation_tick": "当前算法激活 tick。",
        "dt_seconds": "距上次调用的仿真秒。", "output_commit_tick": "本批次输出的固定提交 tick。", "config": "任务授予的只读配置，不包含敌车真值。"}),
    "Module": ("框架模块生命周期。入门时使用生成的包装，不需要自己编写消息或管理进程。", {}),
}

METHOD_TEXT: dict[str, str] = {
    "latest": "读取指定端口的最新 Sample；没有输入时返回 None。",
    "publish": "收集类型化输出，经过 Authority 校验后在固定 tick 提交。",
    "fire": "请求单发开火，返回请求 ID；需任务授权。",
    "setup": "模块创建时初始化一次。", "reset": "新场景或部署时重置算法状态。",
    "update": "按仿真周期调用算法。", "teardown": "关闭模块时释放资源。",
}


def type_name(annotation: Any) -> str:
    return inspect.formatannotation(annotation).replace("typing.", "").replace("~T", "T")


@lru_cache(maxsize=1)
def sdk_reference() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, (description, notes) in TYPE_TEXT.items():
        cls: type = getattr(tankbot, name)
        hints: dict[str, Any] = get_type_hints(cls)
        names: list[str] = [item.name for item in fields(cls)] if is_dataclass(cls) else list(hints)
        members: list[dict[str, str]] = [{"name": key, "type": type_name(hints[key]), "description": notes[key]} for key in names]
        constructor_parts: list[str] = []
        if is_dataclass(cls):
            for item in fields(cls):
                part: str = item.name + ": " + type_name(hints[item.name])
                if item.default is not MISSING:
                    part += " = " + repr(item.default)
                elif item.default_factory is not MISSING:
                    part += " = " + item.default_factory.__name__ + "()"
                constructor_parts.append(part)
        methods: list[dict[str, str]] = []
        method_name: str
        for method_name in METHOD_TEXT:
            if method_name in cls.__dict__:
                signature: inspect.Signature = inspect.signature(getattr(cls, method_name))
                signature = signature.replace(parameters=[p for p in signature.parameters.values() if p.name != "self"])
                methods.append({"name": method_name, "signature": method_name + str(signature), "description": METHOD_TEXT[method_name]})
        constructor: str = name + "(" + ", ".join(constructor_parts) + ")" if is_dataclass(cls) else name + str(inspect.signature(cls))
        result.append({"name": name, "description": description, "constructor": constructor, "fields": members, "methods": methods})
    result.append({"name": "ndarray", "description": "NumPy 数组。C1 返回 float64 的 (4,4) 矩阵；@ 表示矩阵与向量相乘。", "constructor": "np.array(rows, dtype=np.float64) / np.eye(4, dtype=np.float64)",
                   "fields": [{"name": "shape", "type": "tuple[int, ...]", "description": "数组形状；SE(3) 必须是 (4,4)。"},
                              {"name": "dtype", "type": "np.dtype", "description": "元素类型；本关使用 np.float64。"},
                              {"name": "T", "type": "ndarray", "description": "转置。注意转置通常不等于 SE(3) 的逆。"}], "methods": []})
    return result


PYTHON_BASICS: list[dict[str, str]] = [
    {"title": "类型注解", "text": "name: float = 1.0 声明变量；own_pose: Pose2D 声明参数；-> NDArray[np.float64] 声明返回类型。self 是 Python 隐含的当前实例参数。注解帮助阅读，不会替你计算结果。", "code": "distance_m: float = 2.0\nangle_rad: float = math.pi / 2"},
    {"title": "读取字段与构造结果", "text": "用 对象.字段 读取；SDK 数据不可变。创建新结果即可，不修改输入。", "code": "x_m: float = own_pose.x_m\nestimate: TargetEstimate = TargetEstimate(x_m=1.0, y_m=2.0)"},
    {"title": "矩阵与向量", "text": "NumPy 用 [行,列] 索引；@ 是矩阵乘法，* 是逐元素乘法。切片 [:3,:3] 是旋转块，[:3,3] 是平移列。", "code": "T_map_radar: NDArray[np.float64] = np.eye(4, dtype=np.float64)\npoint_radar: NDArray[np.float64] = np.array([2.0, 0.0, 0.0, 1.0])\npoint_map: NDArray[np.float64] = T_map_radar @ point_radar"},
    {"title": "空测量与状态", "text": "tuple[T, ...] 是任意长度的 T 元组；() 表示没有测量。A | None 表示有 A 或没有结果。self.estimate 可以跨 update 调用保留。", "code": "measurement: TargetEstimate\nif measurements:\n    measurement = measurements[0]\n    self.estimate = measurement\nreturn self.estimate"},
    {"title": "只填写算法", "text": "导入、项目结构、仿真时间、消息、测试入口与部署由游戏准备。先保存，再测试，最后部署；重试/部署会清空算法内存，关闭编辑器不会。", "code": "def update(self, measurements: tuple[TargetEstimate, ...], dt: float) -> TargetEstimate | None:\n    return self.estimate"},
]

LESSONS: dict[str, dict[str, Any]] = {
    "c0": {"title": "C0 · 先认识坐标与控制", "summary": "本关不需要编程。先熟悉车头方向、地图方向、炮台与射击。",
           "steps": ["W/S 前后；差速 A/D 转动车体，全向 A/D 横移、Q/E 转向。", "按任务面板要求移动、转向，再用 J/L 瞄准、空格单发。", "地图 +x 向右、+y 向上；yaw 从 +x 逆时针为正，视角不会跟着车体旋转。", "此关明确显示真值。后续关卡会逐步撤回信息，并提供替代观测与算法模板。"],
           "files": [], "default_type": "Pose2D", "functions": [], "aliases": {}},
    "c1": {"title": "C1 · 用 SE(3) 建立两个坐标系之间的关系", "summary": "只实现 radar_to_map：返回一个 NumPy 4×4 矩阵。极坐标展开、点的矩阵乘法和结果发布已由框架处理。",
           "steps": ["打开 perception/transforms.py，只填写 radar_to_map 的 TODO。own_pose 的完整类型和字段见下方签名与类型参考。", "把二维 yaw 写为绕 z 的旋转，把自身 x/y 写入平移列；本关雷达系与车体系重合，z=0。", "前三列分别是雷达 x/y/z 基向量在地图中的方向，第四列是雷达原点在地图中的位置。乘法把这些列按点坐标加权相加。", "在「矩阵实验」里改变位姿和点坐标，逐行观察 T @ p，再运行旋转、平移及方向向量测试。", "保存 → 测试快照 → 部署已测试版本。看到目标估计后手动瞄准命中。"],
           "files": [{"path": "perception/transforms.py", "role": "算法练习：只实现这个矩阵函数。"}],
           "default_type": "Pose2D", "functions": [("perception/transforms.py", TRANSFORMS, "radar_to_map")],
           "aliases": {"own_pose": "Pose2D", "detection": "RadarDetection", "T_map_radar": "ndarray"}},
    "c2": {"title": "C2 · 复用变换，在噪声中保留状态", "summary": "C1 的 SE(3) 矩阵继续使用。你只在 Tracker 中处理已经转换到地图的测量，并保存跨调用的估计。",
           "steps": ["复用 perception/transforms.py，不需要重新实现坐标变换。打开 perception/tracker.py 的 Tracker.update。", "measurements 是 tuple[TargetEstimate, ...]；有测量时可读取 measurements[0].x_m/y_m，丢失时为空元组 ()。", "dt 是仿真秒。__init__ 只初始化一次；把状态保存在 self.estimate 或自定义的带类型字段中。", "尝试平滑、滑动窗口或预测；没有测量时决定保留或预测状态，尚未初始化时可返回 None。", "保存、测试并部署。跟踪巡逻敌车，考虑弹丸飞行时间，击杀后通关；真值误差仅在尝试结束后给出。"],
           "files": [{"path": "perception/tracker.py", "role": "算法练习：初始化状态并完成 update。"}, {"path": "perception/transforms.py", "role": "复用 C1 的矩阵函数。"}],
           "default_type": "TargetEstimate", "functions": [("perception/tracker.py", TRACKER, "update"), ("perception/transforms.py", TRANSFORMS, "radar_to_map")],
           "aliases": {"own_pose": "Pose2D", "detection": "RadarDetection", "measurement": "TargetEstimate", "self.estimate": "TargetEstimate", "T_map_radar": "ndarray"}},
}


def function_reference(path: str, source: str, name: str) -> dict[str, Any]:
    function: ast.FunctionDef = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == name)
    parameters: list[dict[str, str]] = [{"name": arg.arg, "type": ast.unparse(arg.annotation)} for arg in function.args.args if arg.arg != "self"]
    return_type: str = ast.unparse(function.returns)
    return {"path": path, "name": name, "parameters": parameters, "returns": return_type,
            "signature": name + "(" + ", ".join(p["name"] + ": " + p["type"] for p in parameters) + ") -> " + return_type,
            "description": ast.get_docstring(function)}


def learning_bundle(config: dict[str, Any]) -> dict[str, Any]:
    level_id: str | None = config.get("campaign", {}).get("active_level")
    lesson: dict[str, Any] = copy.deepcopy(LESSONS[level_id]) if level_id else {
        "title": "机器人工作区说明", "summary": "示例里程计已提供；可查阅类型并修改自己的算法。", "steps": ["先阅读文件中的类型注解与说明，再保存、测试和部署。"],
        "files": [], "functions": [], "aliases": {}, "default_type": "Pose2D"}
    lesson["functions"] = [function_reference(*entry) for entry in lesson["functions"]]
    lesson["execution"] = "本关无需编程；关闭代码编辑器后使用键盘驾驶。"
    lesson["completion"] = "可查阅类型、修改算法，并保存、测试和部署。"
    lesson["common_errors"] = ["编辑器打开时，驾驶按键用于编辑代码；关闭后才能控制坦克。"]
    if level_id:
        definition: dict[str, Any] = config["campaign"]["levels"][level_id]
        objective: dict[str, Any] = definition["objective"]
        if level_id == "c0":
            lesson["completion"] = f"相对起点移动至少 {objective['movement_m']:g} m、车体转向至少 {objective['turn_rad']:g} rad，并命中靶标 {objective['required_hits']} 次。"
        else:
            lesson["execution"] = (f"框架按 {config['clock']['algorithm_hz']} Hz 仿真频率调度，雷达按 {config['campaign']['radar']['update_hz']} Hz 采样；"
                                   "每个新雷达帧调用一次算法，包括空检测帧。dt 使用仿真秒；部署和重试重新初始化状态。")
            lesson["completion"] = ("发布合法的地图目标估计，并命中靶标 " + str(objective["required_hits"]) + " 次。" if level_id == "c1" else
                                    "把敌车 HP 减到 0 即通关；误差评分在尝试结束后显示，不作为额外门槛。")
            lesson["common_errors"] = (["返回 np.ndarray，形状必须是 (4,4)；不能返回 list 或 TargetEstimate。",
                                          "yaw 已经是弧度，矩阵方向为 radar → map；用 @ 做矩阵乘法，最后一行为 [0,0,0,1]。"] if level_id == "c1" else
                                         ["先检查 measurements 是否为空；没有测量不代表目标坐标为 (0,0)。",
                                          "状态保存在 self 的字段中；dt 单位是秒，不要用真实时间或每次调用都清空状态。"])
    return {"version": "1.0", "template_version": TEMPLATE_VERSION, "lesson": lesson,
            "types": copy.deepcopy(sdk_reference()), "python": copy.deepcopy(PYTHON_BASICS),
            "managed_files": ["campaign_robot.py", "tankbot.json", "contracts/perception.json", "tests/test_coordinates.py"]}
