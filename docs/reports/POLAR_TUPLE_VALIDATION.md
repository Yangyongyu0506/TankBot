# C3/C4 极坐标观测元组验收

日期：2026-10-27。范围：将 PolarTracker 的原始测量输入从 NumPy (N,2) 改为 tuple[PolarTargetEstimate, ...]，同步复用方 C4；决策与接口见 [ADR-0039](../adr/0039-typed-polar-observation-tuples.md)、[28](../28_WEAPONS_PROGRESSIVE_ESTIMATION.md)。C0–C2 与 C5 的 YAML、线上协议、传感器、权限、物理和判定不改。

## 实现与迁移

管理适配器每帧构造不可变元组，字段值逐项来自原 Radar，不预滤波、不转换到全局坐标、不累计历史。空帧为 ()，输入对象的 covariance 为 None；噪声矩阵继续由构造参数提供。自身位姿与内部矩阵仍使用 NumPy。

C3/C4 的模板为 5.0.0，F2 类型参考、参数签名、空帧及迁移示例均从 YAML 提供。measurements[0] 的字段帮助与补全提供 range_m/bearing_rad。旧数组算法文件不会自动重写，需玩家按提示改用字段读取，或在算法内部显式转换为 NumPy。

管理类声明 scaffold_api=polar_tuple@1；升级检查静态解析源码中的声明，不执行玩家代码。旧适配器缺少声明时提示预览更新，避免只换类型注解而实际仍传数组。格式变化/普通注释不影响声明；语法错误交给原生 Python 测试日志。自定义入口不被强制替换。

## 自动化结果

- Python 全量 **183 项通过，106.680 s**，日志 `.m1-cache/polar-tuples/python-tests.log`。
- 新增直接适配器测试确认 tuple/元素类型、原始 r/theta、输入 None 协方差、对象不可变、空帧、重复采样去重、同期位姿与实际 dt，无跨帧累积。
- 新增 C3/C4 升级测试确认旧 Python API 与相同协议端口可区分；升级不覆盖算法，旧 revision 可读；当前注解、教材与运行类型一致。
- 原生数值闭环验证 C3、C4、C5 正常通关；参考 EKF 改为字段读取，其他算法数学过程不变，C5 的装甲输入保持数组。
- Node SDK 类型帮助 **4 项通过**，包含 measurements[0]. 的补全、字段说明和未知对象处理。编辑器 bundle 构建、浏览器源码包准备通过。
- 未修改 SDK 消息类、JSON Schema、协议版本或 Rust 物理实现；不把既有物理报告当成本轮重跑。

## 实际网页与边界

原生与浏览器 WASM/Pyodide 两种真实网页均通过：分别经 CodeMirror 编辑、保存、测试 Ready、部署 Active，依次完成 C3→C4→C5。C3 保留人工武器；C4/C5 由程序自主击杀。

证据为 `.m1-cache/polar-tuples/native-ui.json`、`browser-ui.json` 与对应 tree/running 截图。两种 Runtime 共享新管理适配器，C3/C4 算法通过字段读取实际观测对象；C5 仍读取装甲矩阵。全部复验使用独立源码库、设置与存档，不修改用户日常项目。普通 Python 仍受现有本机运行限制，本次不增加安全隔离能力；其他平台、教学效果与多目标未在本轮验证。
