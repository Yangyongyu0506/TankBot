# Architecture Decision Records

## 目的与状态

ADR 记录为什么选择某条设计路线，供后续 Agent 约束实现和评审变更。初版日期为 2026-10-20，当前更新到玩家依赖与运行反馈（2026-10-25）。`Accepted` 表示当前接受的设计约束；不是实施完成证明。`Proposed` 表示仍需指定实验/审查，不得当成已锁定依赖。`Superseded` 表示被明确编号的新 ADR 完整替代，保留原记录与链接。ADR-0003 已由 M3 实证后的 ADR-0021 替代；ADR-0014 局部修订 0004/0010 的速度接口表达，其余约束仍有效。ADR-0017 局部修订武器阶段与后坐作用模型，未整体废弃 ADR-0015。

| 编号 | 决策 | Status |
| --- | --- | --- |
| [0001](0001-architecture-principles.md) | 纯核心、边界与跨平台原则 | Accepted |
| [0002](0002-core-language-and-physics.md) | 采用经本机原生/浏览器验证的 Rust/Rapier | Accepted |
| [0003](0003-web-frontend.md) | 原 TypeScript/Phaser/CodeMirror 候选，由 0021 替代 | Superseded |
| [0004](0004-json-protocol.md) | JSON、类型化 Envelope 与版本规则 | Accepted |
| [0005](0005-transport-abstraction.md) | 与 Transport 无关的语义与校验 | Accepted |
| [0006](0006-ground-truth-separation.md) | 三层状态与唯一物理权威 | Accepted |
| [0007](0007-view-policy-and-pose-selection.md) | Authority 执行 View Policy 与显式选源 | Accepted |
| [0008](0008-module-contract.md) | Contract、混合调用与渐进 SDK | Accepted |
| [0009](0009-workspace-management.md) | 非覆盖模板、版本化 Workspace | Accepted |
| [0010](0010-simulation-scheduling.md) | 固定 tick、冻结输入与定点提交 | Accepted |
| [0011](0011-determinism-and-replay.md) | 有限确定性与分层 Replay | Accepted |
| [0012](0012-edit-test-deploy.md) | 快照测试、不可变部署与状态重置 | Accepted |
| [0013](0013-python-runtime-isolation.md) | 浏览器/桌面/服务器 Runtime 技术组合 | Proposed |
| [0014](0014-ros-style-velocity-interface.md) | ROS 惯例、cmd_vel/Twist 与控制器 watchdog | Accepted |
| [0015](0015-confirmed-m1-physics-profile.md) | 用户确认的受力/接触/观测模型与单文件参数 | Accepted |
| [0016](0016-wheel-joint-state.md) | 独立 joint_state 类型，保留旧 Encoder 语义 | Accepted |
| [0017](0017-confirmed-weapons-loop.md) | 用户确认的武器物理、幂等单发与授权练习视图 | Accepted |
| [0018](0018-authorized-rendering-timeline.md) | 授权数据时间插值、平移跟随相机与独立外观 | Accepted |
| [0019](0019-fourfold-omni-wheel-layout.md) | 四轮 90° 旋转对称固定全向轮与统一运动学 | Accepted |
| [0020](0020-shared-browser-authority.md) | 浏览器复用 Authority、双 origin 与独立玩家 Worker | Accepted |
| [0021](0021-editor-and-deployment-profile.md) | M3 CodeMirror/Vim、本机版本库与共享部署生命周期 | Accepted |
| [0022](0022-campaign-capabilities-and-evaluation.md) | C0–C2 能力配置、Radar/目标估计与结束后评分 | Accepted |
| [0023](0023-typed-learning-and-se3-exercise.md) | 带类型的逐关说明、NumPy SE(3) 与矩阵实验 | Accepted |
| [0024](0024-gamepad-manual-input.md) | Gamepad API、逐执行器人工仲裁与回中后接管 | Accepted |
| [0025](0025-automatic-python-environment.md) | 首启准备专用 Python 环境、缓存与隔离 Worker 共享解释器 | Accepted |
| [0026](0026-settings-modes-and-campaign-progress.md) | YAML 设置、玩家关卡存档与独立授权的开发者图层 | Accepted |
| [0027](0027-curated-libraries-and-numpy-matrices.md) | 课程库白名单、NumPy 矩阵与兼容边界 | Accepted |
| [0028](0028-bounded-player-runtime-feedback.md) | 有界玩家输出、异常调用栈与 UI 运行日志 | Accepted |
| [0029](0029-attempt-deadlines-and-player-health.md) | 关卡时限、主动结束、玩家 HP 与终局顺序 | Accepted |
| [0030](0030-yaml-parameter-source.md) | YAML 参数源、教学数据与生成测试夹具 | Accepted |
| [0031](0031-multi-module-graph-execution.md) | 多模块图、冻结输入与整图部署 | Accepted |
| [0032](0032-weapons-curriculum-and-armor.md) | Weapons 章节、角加速度、装甲与噪声 | Accepted |
| [0033](0033-declarative-level-plugins.md) | 独立 YAML 关卡、自动发现、声明式规则与独立权限 | Accepted |

## 变更流程与完成条件

新决策使用递增四位编号和英文描述文件名；记录 Context、Decision、Alternatives、Consequences、Status，并给验证或接受条件。修改核心权威、信息边界、调度或公共接口前先定位相关 ADR。重大变更新增替代 ADR，并同步链接、领域规范、Schema、夹具和测试计划；不得只把旧决定悄悄改成另一种含义。

当前接受边界原则和已有证据的 Rust/Rapier 与本地浏览器适配；M3 编辑器在本机 profile 接受，完整平台安全组合保持 Proposed。后续将 Proposed 变成 Accepted 必须引用实验报告、目标平台和限制，不能仅凭“文档已写好”。开放项统一追踪于 [12](../12_VALIDATION_AND_OPEN_QUESTIONS.md)。
