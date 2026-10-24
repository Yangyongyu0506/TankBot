# 19 关卡学习说明、类型工具与 SE(3)

## 目的、范围与要求

2026-10-24 用户补充：所有关卡必须清楚说明输入、输出、数据结构、变量类型与操作步骤；玩家只填写算法。C1 专门学习坐标变换矩阵，函数返回 NumPy 数组形式的 SE(3) 元素，并实际用于矩阵乘法。

本次覆盖所有现有关卡 C0–C2、沙盒类型参考和后续关卡的编写规范。保持现有物理、传感器、权限和击杀条件；二维位姿以 z=0 嵌入 SE(3)。完整三维物理或语言服务器不属于本次范围。

每关说明必须包含：问题与完成条件、需要编辑的文件、函数签名、每个参数/字段的类型和单位、返回值与无结果语义、合成输入输出示例、调用频率/状态生命周期、保存测试部署步骤和常见错误。生成及展示的 Python 参数、局部变量、对象状态必须显式标注类型，函数必须标注返回类型；self、导入名及语言无法就地注解的循环绑定按 Python 惯例处理。继承的已声明状态重新赋值不重复声明。

## C1 的正式函数接口

```python
import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D

def radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:
    T_map_radar: NDArray[np.float64] = np.eye(4, dtype=np.float64)
    # TODO: 填写旋转和平移，完成后返回 T_map_radar。
    raise NotImplementedError("请完成 SE(3) 矩阵")
```

文件为 `perception/transforms.py`。输入的 `own_pose.x_m/y_m` 是地图位置（m），`yaw_rad` 是车头相对地图 +x 的逆时针角（rad）。Radar 与车体系重合。返回值必须是实数 NumPy `ndarray`，shape 为 `(4,4)`；框架转换为 float64。

`T_map_radar = [[R,t],[0,1]]`：前三列是雷达基向量在地图中的方向，第四列是雷达原点在地图中的位置；左乘就是按点坐标加权这些列。本关 `R=Rz(yaw)`，`t=[x,y,0]`。函数返回的是从 radar 到 map 的变换，方向不能写反。

系统把测量展开为 `point_radar=[range*cos(bearing), range*sin(bearing), 0, 1]`，然后在真实运行链内执行：

```python
point_radar: NDArray[np.float64] = radar_point(detection)
point_map: NDArray[np.float64] = T_map_radar @ point_radar
```

`@` 为矩阵乘法，`*` 为逐元素乘法。合成自测：自身 `(1,3,π/2)`、雷达点 `[2,0,0,1]` 应得到 `[1,5,0,1]`；相同方向 `[2,0,0,0]` 得到 `[0,2,0,0]`，不受平移影响。z=0 的场景仍使用标准 4×4 SE(3)，为后续机器人算法保留相同表达。

`tankbot.transforms.validate_se3` 检查 ndarray、实数形状、有限性、最后一行、`R.T @ R=I` 和 `det(R)=+1`。容差来自已有 `validation.numeric_tolerance`，通过只说明矩阵合法，不会把错误矩阵修正成真值。缩放、反射、NaN、3×3 矩阵和普通 list 均拒绝。未填写时的 `NotImplementedError` 由启动脚手架作为“等待实现”处理；独立单元测试会定位 TODO。

矩阵仅在玩家 Runtime 内运算，结果转换为既有 `TargetEstimate` 后按 `target_estimate@1` 发布。Protocol/Topic 没有新增 NumPy 数组编码，玩家无需处理消息。

## 所有关卡的编程与说明

| 阶段 | 玩家需要做什么 | 已提供的内容 |
| --- | --- | --- |
| C0 | 按说明学习操作和世界坐标；无需编程 | 按键、单位、方向、目标与授权真值的解释 |
| C1 | 只实现 `radar_to_map(own_pose) -> NDArray[np.float64]` | import、4×4 脚手架、SE(3) 验证、T @ p、输出适配、旋转/平移/方向测试 |
| C2 | 复用 C1 矩阵，实现 `Tracker.update(measurements, dt) -> TargetEstimate | None` | 地图点元组、空测量/None 语义、带类型状态字段、调用时序与部署说明 |

`host/tankbot_host/learning.py` 是受信内容注册表；每个已注册关卡必须有完整学习说明。公开 DTO 的字段与类型从实际 SDK dataclass/type hints 生成，方法签名从实际方法读取；字段用途和单位单独编写并测试齐全。函数签名从随游戏提供的模板 AST 读取，不执行玩家代码，也不暴露私有世界值。

`GET /api/workspace` 增加 `learning`：当前说明、函数约定、SDK 类型、Python 速查、模板版本和升级状态。它属于启动器管理 API，原生与浏览器共用。内容仅为静态合成示例、SDK 声明和课程说明，不包含当前敌车位姿/路径/私有历史。

## 编辑器内的学习工具

F2 打开代码工作区，默认显示当前关卡说明；F1 或「关卡说明 / 类型」可随时打开、收起辅助面板。四个页签分别是任务说明、类型参考、矩阵实验、Python 速查。说明提供直接打开算法文件的按钮，函数签名固定显示在编辑区上方。

类型参考可搜索类名或字段，如 Pose2D、range_m、ndarray；显示字段类型、单位、构造方式与方法。CodeMirror 悬停和成员补全使用同一份 SDK 元数据；支持显式类型声明与任务形参，Ctrl+Space 可主动补全。它是轻量提示，不声称具备完整 Python/LSP 类型推断。

矩阵实验使用独立合成数据：修改原点 x/y、yaw、源点坐标，查看坐标系基向量、4×4 矩阵和每行点积；切换点 w=1 与方向 w=0，直接观察平移列的作用。它不读取仿真真值或执行玩家代码。所有参考区在弹窗内部滚动，网页仍固定在视口内，窄窗口可返回代码。

## 模板升级与依赖

教学模板版本 `1.2.0`。新关只补不存在的文件；已有算法保留。旧 C1 的 `coordinates.py` 不会被覆盖或删除。旧脚手架测试/部署会提示 `TEACHING_TEMPLATE_UPGRADE_REQUIRED`；玩家在预览中选择「系统脚手架更新」，核对后应用，可一次更新 wrapper/Manifest/Contract/生成测试，算法文件默认 keep，旧 revision 仍可恢复。

原生 NumPy 固定 `2.3.3`，随 `requirements.txt` 安装；其官方支持范围包含 Python 3.11–3.14，满足当前原生解释器。浏览器使用锁定 Pyodide 0.29.5 提供的 NumPy `2.2.5` wheel；摘要及字节数加入 browser-assets.lock，prepare 工具下载并验证，玩家 Worker 自动加载。本机与浏览器版本分别验证，不承诺 NumPy 跨版本位级相同。[NumPy 发行说明](https://numpy.org/doc/stable/release/2.3.3-notes.html)、[Pyodide 包加载](https://pyodide.org/en/latest/usage/loading-packages.html)。

玩家不配置 pip、网络或 Workspace 依赖。NumPy 是应用预装能力；Manifest 的 dependencies 仍为空，不授予联网安装权限。启动握手记录实际 NumPy 版本，测试环境摘要包含运行包版本和依赖锁文件，版本变化会使旧 Ready 失效。

## 取舍、未决项与验收

保留轻量 CodeMirror 和元数据提示，避免为入门课程部署语言服务器。通过官方类型、显式模板与交互说明减少框架学习成本；后续可验证完整跨文件类型诊断、更多三维旋转实验和数学符号输入。现阶段只验证已有平台 profile。

验收覆盖所有关卡说明齐全、模板参数/变量/返回注解、SDK 字段一致、矩阵确实进入闭环、点/方向/逆变换、非法 SE(3)、旧算法无损迁移、真实浏览器类型补全与矩阵实验，以及原生/Pyodide 的三关流程。证据见 [学习工具验收报告](reports/LEARNING_VALIDATION.md) 与对应测试。
