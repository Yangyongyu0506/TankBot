# TankBot 技术文档索引

## 阅读方式与规范状态

文档基线：`design-0.2`，更新日期：2026-10-21。初版检查时只有根目录 `AGENTS.md`；当前已存在文档初始化提交，仍没有游戏实现或工具链。本次修订按 ROS 习惯调整速度接口，见 [ADR-0014](adr/0014-ros-style-velocity-interface.md)。本目录描述未来系统，不宣称已经完成开发。

“必须／不得”为设计约束；“建议／拟采用”为待验证方案。Accepted ADR 表示接受设计原则或接口方向，不表示实现或平台验证完成；Proposed 技术不得当作既成依赖。协议 `1.0` 是**未发布草案**，首次发布前由兼容性审查冻结；发布后执行版本规则。

设计权威顺序：本轮明确需求 → Accepted ADR → 对应领域规范与 Schema → 示例与路线图。发现冲突时记录并修正文档，不自行绕过边界。Schema 只裁决结构，领域规范裁决时间、权限和语义。更改公共接口必须同步检查所有引用。

## 文档地图

| 文档 | 负责的设计与接口 |
| --- | --- |
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
