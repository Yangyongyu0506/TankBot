"""Player-facing explanations from trusted lesson text and actual SDK type declarations."""
import ast
import copy
from dataclasses import MISSING, fields, is_dataclass
import inspect
from functools import lru_cache
from typing import Any, get_type_hints
import tankbot
from tankbot._imports import load_policy
from typing import get_args, get_origin
import types
import numpy as np
from .campaign_templates import template_version, TRANSFORMS, TRACKER, MANAGED_FILES


TYPE_TEXT: dict[str, tuple[str, dict[str, str]]] = {
    "TargetPoints": ("当前帧地图坐标测量矩阵，不包含历史。", {"positions_m":"只读 float64 NumPy 数组，shape=(N,2)，列为 x/y，单位 m；无检测时 shape=(0,2)。"}),
    "TargetPoseEstimate": ("玩家估计的敌车底盘中心与车头朝向，与自身位姿完全分离。", {
        "x_m":"敌车中心在 map 中的 x，m。","y_m":"敌车中心在 map 中的 y，m。","yaw_rad":"敌车车头相对 map +x 的逆时针角，rad，范围 [-π,π)。",
        "covariance":"None 或只读 (3,3) NumPy 协方差，对应 x/y/yaw；原地转向时 yaw 不可直接观测。"}),
    "AimInput": ("自瞄函数的授权输入；数组都是只读 NumPy，玩家无需处理 Topic。", {
        "target_xy":"None 或 shape=(2,) 的地图目标位置 [x,y]，m；C4 仍为敌车底盘中心。",
        "target_age_s":"在本批控制提交时，目标估计已经过去的仿真秒；包含等待提交的延迟。",
        "own_pose":"shape=(3,) 的系统自身位姿 [x,y,yaw]，单位 m、rad。Weapons 阶段不要求估计自己。",
        "turret_angle_rad":"炮台相对车体的累计角，rad；可连续旋转。","turret_rate_radps":"炮台相对角速度，rad/s。",
        "weapon_ready":"本机是否已冷却，bool。","target_yaw_rad":"C3 为 None；C4 为玩家估计的敌车朝向，rad。不是雷达方位角。"}),
    "AimOutput": ("算法的自瞄结果，由框架转换为合法控制消息。", {"acceleration_radps2":"炮台相对角加速度目标，rad/s²；不能直接写角度/角速度。","fire":"bool，True 请求单发；框架处理冷却和请求 ID。"}),
    "TurretAcceleration": ("炮台相对角加速度 Topic 的类型化负载。", {"acceleration_radps2":"目标角加速度，rad/s²；真实响应仍由受限力矩和双刚体动力学决定。"}),
    "Pose2D": ("自身的二维位姿，可由任务授权提供；位置在 map 中，车头方向用 yaw 表示。", {
        "x_m": "地图横坐标，单位 m，向右为正。", "y_m": "地图纵坐标，单位 m，向上为正。",
        "yaw_rad": "车头相对地图 +x 的逆时针角，单位 rad；π/2 表示朝向 +y。",
        "covariance": "None 或只读 float64 NumPy 矩阵，shape=(3,3)，依次对应 x、y、yaw；本关可以忽略。",
        "child_frame_id": "被描述的车体系名称，通常为 base_link；本关可以忽略。"}),
    "RadarDetection": ("一次雷达检测。先在车体系里测量，不能直接当作地图坐标。", {
        "observation_id": "仅本次观测的标签；不能用它识别跨帧的同一敌车。",
        "range_m": "传感器中心到目标中心的距离，单位 m。",
        "bearing_rad": "相对车头的方位角，单位 rad；前方为 0，左侧为正。"}),
    "RadarData": ("一帧雷达数据。没有检测时 detections 是空元组 ()。", {"detections": "不可变的 RadarDetection 元组；逐项读取，不需要解析 JSON。"}),
    "TargetEstimate": ("算法在 map 中估计的目标位置。C2 跟踪器返回这个值；C1 的矩阵结果由框架转换为它。", {
        "x_m": "目标估计的地图横坐标，单位 m。", "y_m": "目标估计的地图纵坐标，单位 m。",
        "covariance": "None 或只读 float64 NumPy 矩阵，shape=(2,2)，对应 x、y；入门时保留 None。"}),
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
    if get_origin(annotation) is np.ndarray:
        return "NDArray[np.float64]"
    if get_origin(annotation) is types.UnionType:
        return " | ".join("None" if item is type(None) else type_name(item) for item in get_args(annotation))
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
    result.append({"name": "ndarray", "description": "NumPy 数组。SE(3) 转换返回 float64 的 (4,4) 矩阵；@ 表示矩阵与向量相乘。", "constructor": "np.array(rows, dtype=np.float64) / np.eye(4, dtype=np.float64)",
                   "fields": [{"name": "shape", "type": "tuple[int, ...]", "description": "数组形状；SE(3) 必须是 (4,4)。"},
                              {"name": "dtype", "type": "np.dtype", "description": "元素类型；本关使用 np.float64。"},
                              {"name": "T", "type": "ndarray", "description": "转置。注意转置通常不等于 SE(3) 的逆。"}], "methods": []})
    return result


PYTHON_BASICS: list[dict[str, str]] = [
    {"title": "类型注解", "text": "name: float = 1.0 声明变量；own_pose: Pose2D 声明参数；-> NDArray[np.float64] 声明返回类型。self 是 Python 隐含的当前实例参数。注解帮助阅读，不会替你计算结果。", "code": "distance_m: float = 2.0\nangle_rad: float = math.pi / 2"},
    {"title": "读取字段与构造结果", "text": "用 对象.字段 读取；SDK 数据不可变。创建新结果即可，不修改输入。", "code": "x_m: float = own_pose.x_m\nestimate: TargetEstimate = TargetEstimate(x_m=1.0, y_m=2.0)"},
    {"title": "矩阵与向量", "text": "NumPy 用 [行,列] 索引；@ 是矩阵乘法，* 是逐元素乘法。切片 [:3,:3] 是旋转块，[:3,3] 是平移列。", "code": "T_map_radar: NDArray[np.float64] = np.eye(4, dtype=np.float64)\npoint_radar: NDArray[np.float64] = np.array([2.0, 0.0, 0.0, 1.0])\npoint_map: NDArray[np.float64] = T_map_radar @ point_radar"},
    {"title": "空测量与状态", "text": "measurements 是本次采样的目标集合，不是历史轨迹；当前单目标场景长度为 0 或 1。() 表示本次没有检测。self.estimate 保存一个当前估计。", "code": "measurement: TargetEstimate\nif measurements:\n    measurement = measurements[0]\n    self.estimate = measurement\nreturn self.estimate"},
    {"title": "NumPy 矩阵与测量数组", "text": "矩阵使用 np.ndarray。target_positions 将本次检测整理为 (N,2) 的 float64 数组，列为 x/y；丢失时 shape=(0,2)，不会追加历史。协方差也是二维 NumPy 数组。", "code": "from tankbot.transforms import target_positions\nxy: NDArray[np.float64] = target_positions(measurements)\nP: NDArray[np.float64] = np.eye(2, dtype=np.float64)\nestimate: TargetEstimate = TargetEstimate(x_m=1.0, y_m=2.0, covariance=P)"},
    {"title": "只填写算法", "text": "导入、项目结构、仿真时间、消息、测试入口与部署由游戏准备。先保存，再测试，最后部署；重试/部署会清空算法内存，关闭编辑器不会。", "code": "def update(self, measurements: tuple[TargetEstimate, ...], dt: float) -> TargetEstimate | None:\n    return self.estimate"},
]

def function_reference(path: str, source: str, name: str) -> dict[str, Any]:
    function: ast.FunctionDef = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == name)
    parameters: list[dict[str, str]] = [{"name": arg.arg, "type": ast.unparse(arg.annotation)} for arg in function.args.args if arg.arg != "self"]
    return_type: str = ast.unparse(function.returns)
    return {"path": path, "name": name, "parameters": parameters, "returns": return_type,
            "signature": name + "(" + ", ".join(p["name"] + ": " + p["type"] for p in parameters) + ") -> " + return_type,
            "description": ast.get_docstring(function)}


def learning_bundle(config: dict[str, Any]) -> dict[str, Any]:
    level_id: str | None = config.get("campaign", {}).get("active_level")
    lesson: dict[str, Any] = copy.deepcopy(config["campaign"]["lessons"][level_id]) if level_id else {
        "title": "机器人工作区说明", "summary": "示例里程计已提供；可查阅类型并修改自己的算法。", "steps": ["先阅读文件中的类型注解与说明，再保存、测试和部署。"],
        "files": [], "functions": [], "aliases": {}, "default_type": "Pose2D"}
    from .workspace import starter
    sources=starter(config)
    if level_id:
        definition=config["campaign"]["levels"][level_id]
        lesson=copy.deepcopy(definition["tutorial"]["lesson"])
        health=definition["target"].get("health",{})
        context={**definition["rules"]["parameters"],"time_limit_s":definition["time_limit_s"],"max_hp":health.get("max_hp"),"damage_per_hit":health.get("damage_per_hit"),"algorithm_hz":config["clock"]["algorithm_hz"]}
        if definition["radar"]:context.update(radar_hz=definition["radar"]["update_hz"],**definition["radar"]["noise"])
        lesson["completion"]=lesson["completion"].format(**context)
        lesson["execution"]=lesson["execution"].format(**context)
        if "calibration" in lesson:
            target=definition["target"];motion=target.get("motion",{})
            length,width=config["body"]["length_m"],config["body"]["width_m"]
            import math
            public={"target_drive_model":motion.get("chassis"),"target_forward_only":motion.get("forward_speed_mps",0)>0,
                "wheel_radius_m":config["wheels"]["radius_m"],"differential_track_m":config["wheels"]["differential_track_m"],
                "body_length_m":length,"body_width_m":width,"projectile_speed_mps":config["weapons"]["projectile"]["relative_speed_mps"],
                "max_acceleration_radps2":config["weapons"]["turret"]["acceleration_control"]["max_relative_acceleration_radps2"],
                "armor_width_m":target.get("armor",{}).get("width_m"),"armor_mounts":[[length/2,0,0],[-length/2,0,-math.pi],[0,width/2,math.pi/2],[0,-width/2,-math.pi/2]]}
            lesson["calibration"]={key:public[value["source"]] if "source" in value else value["text"] for key,value in lesson["calibration"].items()}
    else:
        lesson.update(execution="本关无需编程；关闭代码编辑器后使用键盘驾驶。",completion="可查阅类型、修改算法，并保存、测试和部署。",common_errors=["编辑器打开时，驾驶按键用于编辑代码；关闭后才能控制坦克。"])
    lesson["functions"]=[function_reference(entry["path"],sources[entry["path"]],entry["name"]) for entry in lesson["functions"]]
    types_reference=copy.deepcopy(sdk_reference())
    for item in types_reference:
        notes=lesson.get("type_notes",{}).get(item["name"])
        if notes:
            item["description"]=notes["description"]
            for field in item["fields"]:field["description"]=notes["fields"][field["name"]]
    lesson.pop("type_notes",None)
    from .campaign_templates import framework_upgrade
    managed = framework_upgrade(config,{})["managed_files"]
    return {"version": "1.0", "template_version": template_version(config), "lesson": lesson,
            "dependencies": load_policy(),
            "types": types_reference, "python": copy.deepcopy(PYTHON_BASICS),
            "testing": {"checks":[text.format(test_batches=config["workspace"]["test_batches"]) for text in definition["tutorial"]["testing"]["checks"]],"meaning":definition["tutorial"]["testing"]["meaning"]} if level_id else {"checks":["Python 语法、合同、单元测试和授权仿真。"],"meaning":"通过后可部署。"},
            "managed_files": list(managed)}
