# 23 玩家源码、课程依赖与 NumPy 矩阵

## 目的与范围

明确玩家代码跨关卡的所有权、可用依赖和矩阵表达。2026-10-25 用户要求限制外部算法库，保留亲自实现算法的教学目标，并优先使用 NumPy 表示矩阵。本规范适用于原生和浏览器的玩家 Runtime，包含开发者模式；游戏宿主自身依赖不是玩家库授权。

## 源码保存与运行状态

当前保存的是**所有已保存文件的完整内容**，不只保存 TODO。`WorkspaceAPI.unlock()` 新关只补缺失文件，已有算法、自建工具、框架、测试和 JSON 均逐字节保留。C0 也建立空 `perception/__init__.py`，使共用框架的类型引用有明确项目命名空间，不提前提供后续算法实现。

未保存的编辑器草稿不是磁盘存档；切关前要求保存。部署、重试或切关会重新初始化 Python 内存，如 `self.estimate`；源码文件继续保留。重新启动不会自动运行未测试草稿，仍需 Test/Deploy。

因此当前不存在“注释对之外自动重置”的代码区域，也不要求玩家把代码塞在保护区中。若未来改为混合文件自动重生成，必须另加成对保护标记、事务合并和逐字节保留测试，不能推断注释外代码可删除。当前系统框架升级仍先预览、明确确认，再创建新 revision，旧内容可恢复；见 [06](06_WORKSPACE_AND_TEMPLATES.md)、[19](19_LEARNING_GUIDES_AND_SE3.md)。

## 课程依赖白名单

[config/player-dependencies.yaml](../config/player-dependencies.yaml) 是受信策略，结构由 [Schema](schemas/player-dependencies.schema.json) 定义。玩家 Manifest 不能改变它：

| 范围 | 当前允许内容 |
| --- | --- |
| 第三方库 | 仅 `numpy`，含常用线性代数、数组、基础统计与类型注解 |
| 基础标准库 | `math`、`cmath`、`statistics`、`random`、`collections`、`heapq`、`bisect`、`itertools` 等；完整列表在策略文件与关卡说明 |
| SDK | `tankbot`、`tankbot.transforms` 公共接口 |
| 自建代码 | 当前 Workspace 内的多文件模块与相对 import |
| 测试工具 | `unittest` 仅供 `tests/` 下的测试文件 |

SciPy、FilterPy、scikit-learn、机器人算法封装库等默认不开放。`pip`、`micropip`、`subprocess`、`importlib` 等安装/加载通路也不列为玩家导入接口。`tankbot.json.dependencies` 当前必须为空；NumPy 是课程预装库，不要求学生声明或安装。

游戏启动器负责自动准备锁定的应用环境，浏览器准备脚本负责锁定 Pyodide/NumPy 资源；这些行为不意味着玩家可以安装任意包。新增课程依赖必须由维护者审查教学影响，更新策略、两平台资源、界面说明与测试，并重新启动验证。原生宿主的 PyYAML/jsonschema 等即使已安装，也不因此成为玩家可导入库。

## 导入检查与错误反馈

Authority 在 Test 前静态检查整个 Python 项目，包括测试、未调用函数中的 import 和 `from`。受控 Runtime 为项目源码安装独立 loader 与导入检查，普通 `__import__(variable)` 也按白名单验证；即使同名包已在解释器中加载，也不会直接放行。库自身的内部实现依赖由库加载，不要求玩家了解或配置。

禁止导入返回 `DEPENDENCY_NOT_ALLOWED`。静态错误带项目路径/行号；动态错误进入测试或运行日志。原生初始项目与浏览器初始项目也检查，不能从启动种子绕开 Test。白名单内容进入部署环境摘要，旧测试不能用于另一套依赖策略。

这是课程导入规则，不能替代 OS 沙箱，也不能证明代码原创；有意使用 Python 反射、读取本机文件或复制算法源码仍属于既有单机信任边界。原生只运行本人可信代码，浏览器不宣称防设备所有者修改。Arena 的服务器隔离与资源硬限制仍按 [08](08_RUNTIME_AND_SECURITY.md) 实施。

## 矩阵与对象集合

数值矩阵使用 `NDArray[np.float64]`，不使用 `numpy.matrix`。约定：

| 数据 | SDK 形状 |
| --- | --- |
| `T_map_radar` | `(4, 4)` SE(3)，C1 已使用实际矩阵乘法 |
| `Pose2D.covariance` | `None` 或只读 `(3, 3)` ndarray，顺序 x/y/yaw |
| `TargetEstimate.covariance` | `None` 或只读 `(2, 2)` ndarray，顺序 x/y |
| `target_positions(measurements)` | 可写 `(N, 2)` ndarray，每行是 map 中的 x/y，单位 m |

协方差矩阵复制为不可写的独立数据，避免修改输入数组影响已提交值；需要更新时使用 `.copy()` 计算并构造新结果。拒绝形状错误、复数/字符串/对象矩阵；PSD、时间、坐标系和权限仍由 Authority 验证。旧扁平 list/tuple 构造参数继续读取并转换为二维数组；旧算法若按扁平下标读取协方差，应改用 `P[i,j]` 或显式 `P.ravel()[k]`。

Protocol 的 JSON 协方差仍是行优先长度 4/9 数组，SDK 在发布边界扁平化，接收时恢复 ndarray，不修改已存在的消息 Schema。SDK `0.1.0` 仍为未发布开发 profile，本轮显式修订协方差读接口；不能把构造参数兼容误读为二维数组与旧 tuple 完全等价。

```python
import numpy as np
from numpy.typing import NDArray
from tankbot import TargetEstimate
from tankbot.transforms import target_positions

def numeric_measurements(measurements: tuple[TargetEstimate, ...]) -> NDArray[np.float64]:
    xy: NDArray[np.float64] = target_positions(measurements)
    return xy
```

C2 的 `measurements` 是**本次采样的对象集合**，当前单敌车场景长度为 0 或 1，不是历史。每个对象含 x/y 及可空协方差；不含 yaw 或累计轨迹。`self.estimate` 保存一个当前 `TargetEstimate | None`。对象集合、轮名、文件列表不是矩阵，不强制改成 `dtype=object` 的 NumPy 数组。

`target_positions(())` 始终返回 `(0,2)` 数组；它不会追加历史。若玩家主动保存历史，应使用有长度上限的窗口，而非无限 append/拼接。当前 Authority 真值评分历史默认最多 61 个 tick，私有验收 replay 最多 36000 tick，显示轨迹最多 300 点；有界缓存不等于整个解释器拥有硬内存配额。长时 RSS/OOM 验收仍开放。

## 验收与开放项

测试需覆盖全部文件跨关逐字节保留、禁止库静态/动态导入、预加载包拒绝、相对 import、两平台 NumPy 协方差往返及只读性、C2 空输入与有界数组大小。证据见 [玩家 Runtime 验收](reports/PLAYER_RUNTIME_VALIDATION.md)。当前不提供第三方库自由安装；将来只按新的教学需求审查少量基础库。完整平台与长期资源问题见 [M1–M4 核对](reports/M1_M4_STATUS_AUDIT.md)。

矩阵 API 依据为 [NumPy ndarray](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html) 与 [buffer 视图](https://numpy.org/doc/stable/reference/generated/numpy.frombuffer.html)；浏览器可加载的包与原生包并不相同，参考 [Pyodide 包加载文档](https://pyodide.org/en/stable/usage/loading-packages.html)，实际版本以项目锁文件为准。
