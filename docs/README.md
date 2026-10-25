# TankBot 技术文档索引

## 阅读方式与规范状态

文档基线：`m5-level-plugins-1.0`，更新日期：2026-10-25。已完成 M1/M1b、M2 本机浏览器/Transport、M3 编辑部署和 M4 C0–C2 教学闭环验收：实现与限制见 [运行入口](../README.md)、[M4 验证报告](reports/M4_VALIDATION.md)；模型由用户逐项确认，见 [13](13_PHYSICS_MODEL_DECISIONS.md)、[18](18_CAMPAIGN_DESIGN.md)。M5 已实现多模块图、C3/C4 Weapons、角加速度与装甲，当前边界及验收见 [26](26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)、[M5 报告](reports/M5_VALIDATION.md)。现有五关已重构为独立 YAML 插件，见 [27](27_LEVEL_PLUGIN_ARCHITECTURE.md)。Locomotion、自身定位课程、建图、规划与 Arena 尚未实现。

“必须／不得”为设计约束；“建议／拟采用”为待验证方案。Accepted ADR 表示接受设计原则或接口方向，不表示实现或平台验证完成；Proposed 技术不得当作既成依赖。协议 `1.0` 是**未发布草案**，首次发布前由兼容性审查冻结；发布后执行版本规则。

设计权威顺序：本轮明确需求 → Accepted ADR → 对应领域规范与 Schema → 示例与路线图。发现冲突时记录并修正文档，不自行绕过边界。Schema 只裁决结构，领域规范裁决时间、权限和语义。更改公共接口必须同步检查所有引用。

## 文档地图

| 文档 | 负责的设计与接口 |
| --- | --- |
| [26 多模块与 Weapons](26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md) | M5 图、调度、章节、C3/C4 控制与装甲边界 |
| [27 YAML 关卡插件](27_LEVEL_PLUGIN_ARCHITECTURE.md) | 五关审计、Schema、自动发现/生命周期、组件、权限、规则与迁移 |
| [关卡编写指南](../levels/README.md) | 配置来源、已有组件、校验、启动与扩展流程 |
| [关卡插件验收](reports/LEVEL_PLUGINS_VALIDATION.md) | 冻结基线、旧源码/存档、临时插件和两种 Runtime 五关通关 |
| [01 项目愿景](01_PROJECT_VISION.md) | 目标、范围、假设、模式与成功标准 |
| [02 系统架构](02_SYSTEM_ARCHITECTURE.md) | 模块依赖、三种架构视角、技术选型、部署 |
| [03 协议规范](03_PROTOCOL_SPECIFICATION.md) | Envelope、频道、版本、Transport、校验链 |
| [04 状态与视图](04_STATE_AND_VIEW_MODEL.md) | 三层状态、Pose Provider、Selector、权限与泄漏 |
| [05 机器人模块](05_ROBOT_MODULE_SYSTEM.md) | Python 类型、Contract、调度与渐进式 API |
| [06 Workspace 与模板](06_WORKSPACE_AND_TEMPLATES.md) | Manifest、迁移、持久化、Edit/Test/Deploy |
| [07 仿真](07_SIMULATION_DESIGN.md) | 固定步长、异步截止、物理、噪声与 Replay |
| [08 Runtime 与安全](08_RUNTIME_AND_SECURITY.md) | 威胁模型、平台隔离、资源预算与 Arena |
| [09 关卡](09_LEVEL_DESIGN.md) | 能力接管、任务驱动教学、Lab 与可玩性 |
| [10 路线图](10_DEVELOPMENT_ROADMAP.md) | 依赖、交付物、验收、风险与首个 MVP |
| [11 关键问题](11_CRITICAL_QUESTIONS.md) | Q1–Q15 的结论、理由、风险与追踪 |
| [12 验证与待办](12_VALIDATION_AND_OPEN_QUESTIONS.md) | 一致性检查、需求追踪、未决项与研究来源 |
| [13 物理确认记录](13_PHYSICS_MODEL_DECISIONS.md) | 用户逐项确认、伺服/轮组/IMU 方程、历史武器模型与 M1b 修订 |
| [14 武器设计与确认](14_WEAPONS_DESIGN.md) | M1b 范围、控制/开火接口、共同确认、数值近似及验收 |
| [15 渲染设计](15_RENDERING_DESIGN.md) | 多频率时间插值、固定世界朝向相机、独立底盘外观 |
| [16 浏览器 Runtime](16_BROWSER_RUNTIME.md) | 共享 Authority、私有 WASM ABI、独立 origin、加载/截止与平台限制 |
| [17 编辑器与部署](17_EDITOR_AND_DEPLOYMENT.md) | M3 存储、Manifest profile、测试、原子激活、回滚和管理 API |
| [18 教学关卡](18_CAMPAIGN_DESIGN.md) | M4 C0–C2、Radar、目标估计、巡逻敌车与血量通关 |
| [19 学习说明与 SE(3)](19_LEARNING_GUIDES_AND_SE3.md) | 所有关卡的类型/步骤、编辑器帮助、矩阵实验、NumPy 与模板升级 |
| [20 手柄驱动](20_GAMEPAD_INPUT.md) | 标准/自定义映射、模拟量、人工仲裁、回中、断连与编辑隔离 |
| [21 首次启动依赖](21_DEPENDENCY_BOOTSTRAP.md) | 无 pip 环境引导、专用解释器、缓存/离线、并发与重试 |
| [22 设置与游戏模式](22_SETTINGS_MODES_AND_PROGRESS.md) | YAML 改键、开发者图层、玩家关卡解锁与存档 |
| [23 玩家代码与依赖](23_PLAYER_CODE_AND_LIBRARIES.md) | 完整源码保留、课程库白名单与 NumPy 矩阵 |
| [24 运行日志](24_RUNTIME_LOGS.md) | 程序输出、traceback、版本与源码定位 |
| [Python 测试日志验收](reports/PYTHON_TEST_LOG_VALIDATION.md) | 原生测试输出、异常摘要、连续调用栈与两种 Runtime 实际调试 |
| [25 计时、生命与参数](25_ATTEMPT_RULES_AND_CONFIGURATION.md) | 60/60/120 秒、主动结束、玩家死亡、YAML 参数源与生成夹具 |
| [关卡规则验收](reports/ATTEMPT_RULES_VALIDATION.md) | 准备/部署计时、终局边界、反弹自伤和原生/WASM 界面 |
| [M1–M4 核对](reports/M1_M4_STATUS_AUDIT.md) | 当前完成范围、平台/资源/教学开放项 |
| [玩家 Runtime 验收](reports/PLAYER_RUNTIME_VALIDATION.md) | 依赖拒绝、NumPy 往返、日志与恢复 |
| [设置与模式验收](reports/SETTINGS_VALIDATION.md) | 两种 Runtime 的改键、实际通关持久化、图层与撤权 |
| [Python 启动验收](reports/PYTHON_BOOTSTRAP_VALIDATION.md) | 缺包系统直启 C0、原生 Worker、离线新环境与 92 项回归 |
| [手柄验收](reports/GAMEPAD_VALIDATION.md) | 两种 Runtime / 两种底盘的输入闭环、模拟设备及硬件验证边界 |
| [学习工具验收](reports/LEARNING_VALIDATION.md) | SE(3) 真实运算、逐关说明、类型补全、矩阵实验与无损升级 |
| [教学升级验收](reports/TEACHING_UPGRADE_VALIDATION.md) | 旧框架引导、测试范围说明、Ready 点亮部署与算法保留 |
| [M4 验收](reports/M4_VALIDATION.md) | 原生/Firefox 三关通关、两种跟踪法、来源保留与权限证据 |
| [M3 验收](reports/M3_VALIDATION.md) | 原生/Firefox 多文件编辑、快照摘要、失败恢复和焦点证据 |
| [M1 收尾复核](reports/M1_CLOSEOUT.md) | 路线图逐项检查、当前配置与历史证据范围 |
| [M2 验收](reports/M2_VALIDATION.md) | 真实浏览器双 Worker、故障、49 个夹具与平台矩阵 |
| [全向轮验收](reports/OMNI_VALIDATION.md) | 90° 固定全向轮几何、正反解、闭环与浏览器证据 |
| [渲染验收](reports/RENDERING_VALIDATION.md) | 实际显示帧、相机与两底盘对比 |
| [M1 验证报告](reports/M1_VALIDATION.md) | 当前实现范围、实际命令、证据与平台限制 |
| [M1b 验证报告](reports/M1B_VALIDATION.md) | 武器、SDK、浏览器与原生/WASM 证据及限制 |
| [ADR 索引](adr/README.md) | 决策状态、替代方案与变更流程 |
| [Schema 与样例](schemas/README.md) | 可机读的协议、模块、Workspace、底盘配置草案及正反样例 |

建议先读 01 → 02 → 04 → 03 → 05，再按任务阅读其他领域。开始实现前阅读对应 Accepted ADR 和验收条件。

## 统一术语

| 术语 | 唯一定义 |
| --- | --- |
| `Authority` | 承担权威边界的逻辑角色；本地为 Core Host，联机为服务器 |
| `Game Core` | 无 UI、无 Python、无网络依赖的仿真与规则库 |
| `Ground Truth` | Core 内部唯一权威物理状态 |
| `Estimated State` | 玩家输出的估计，与真实状态允许不同 |
| `View Policy` | 对主体、数据来源和表现通道的可见性策略 |
| `View Gateway` | 在 Authority 内执行策略、生成 `PlayerViewSnapshot` |
| `Robot Runtime` | 执行不可信 Python 项目的隔离环境 |
| `Runtime Supervisor` | 可信宿主，管理 Runtime、截止、部署与消息校验 |
| `Workspace` / `Deployment` | 可编辑项目／不可变的代码与配置快照 |
| `run_id` | 一次仿真时间纪元；重置或 seek 后必须更换 |
| `simulation_tick` | 消息描述的仿真逻辑时刻，非网络到达时刻 |

所有示例使用米、秒、弧度、右手平面坐标；具体规则见 03。SDK 类型名、频道和字段不得另取近义别名。
