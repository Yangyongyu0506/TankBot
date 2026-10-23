# TankBot 技术文档索引

## 阅读方式与规范状态

文档基线：`m3-0.1`，更新日期：2026-10-23。已完成 M1/M1b 收尾、M2 本机浏览器/Transport 和 M3 编辑部署验收：实现与限制见 [运行入口](../README.md)、[M1b 验证报告](reports/M1B_VALIDATION.md)；物理模型由用户逐项确认，见 [13](13_PHYSICS_MODEL_DECISIONS.md)。其余功能仍为后续设计，不能把目录完整当作开发完成。

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
| [13 物理确认记录](13_PHYSICS_MODEL_DECISIONS.md) | 用户逐项确认、伺服/轮组/IMU 方程、历史武器模型与 M1b 修订 |
| [14 武器设计与确认](14_WEAPONS_DESIGN.md) | M1b 范围、控制/开火接口、共同确认、数值近似及验收 |
| [15 渲染设计](15_RENDERING_DESIGN.md) | 多频率时间插值、固定世界朝向相机、独立底盘外观 |
| [16 浏览器 Runtime](16_BROWSER_RUNTIME.md) | 共享 Authority、私有 WASM ABI、独立 origin、加载/截止与平台限制 |
| [17 编辑器与部署](17_EDITOR_AND_DEPLOYMENT.md) | M3 存储、Manifest profile、测试、原子激活、回滚和管理 API |
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
