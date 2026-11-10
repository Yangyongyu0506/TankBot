# 当前文档状态同步（2026-11-10）

## 核对基线与证据层次

本次开始时 HEAD 为 `7c065ab`（`1110 Fixed 20ms limitation problem`），`git status --porcelain=v1` 为空。任务描述中的“未提交 Runtime 改动”在此基线已提交；本轮不将它们描述为待合入工作。开始编辑前已保存 552 个受版本管理或未忽略文件的 SHA-256，用于收尾核对。本文是新核对记录，不改写既有验收报告或原始 JSON。

以下事实先从当前代码、YAML、Schema和检查入口提取，再用于修订文档；通过Serena定位execution_profiles、experiments、workspace_maintenance等符号/职责，结合调用处与实际配置核查。历史报告只证明其记录的构建、平台和操作，不代表本轮重新执行了那些流程。

| 领域 | 已提交的当前事实 | 实现 / 配置证据 | 既有验证与限制 |
| --- | --- | --- | --- |
| 配置与课程 | `config_version=2.1`；自动发现十一关：公共 c0、Weapons c1–c5、Navigation c0–c4 | [game.yaml](../../config/game.yaml)、[levels](../../levels/README.md)、[level_plugins.py](../../host/tankbot_host/level_plugins.py) | 历史五关迁移和后续增量分别验收，不能将原五关报告当作十一关报告 |
| 进度 | c0 后同时开放 c1 / navigation.c0；其后各分支按 prerequisites；order 不授予权限 | [progression.py](../../host/tankbot_host/progression.py)、[application.py](../../host/tankbot_host/application.py)、[ADR-0049](../adr/0049-branching-course-progression.md) | [双主线报告](BRANCHING_PROGRESSION_VALIDATION.md)记录当时九关；版本1非连续完成集合合法 |
| 仿真与场景 | Rust/Rapier权威物理；完整底盘模型、传感器实例和已解析场景；Radar、生命规则、轮电压电机已实现 | [32](../32_RESOLVED_SCENE_AND_COMPONENTS.md)、[33](../33_NAVIGATION_MOTION_CONTROL.md)、[config/chassis](../../config/chassis/differential.yaml) | [仿真器报告](SIMULATOR_REFACTOR_VALIDATION.md)；轮滑、全向轮电机扩展仍未实现 |
| 导航 | 已有轮控、里程计、GPS/EKF、航点闭环、连续路径追踪 | [35](../35_NAVIGATION_GPS_LOCALIZATION.md)、[37](../37_NAVIGATION_WAYPOINT_CONTROL.md)、[40](../40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)、[path_generation.py](../../host/tankbot_host/path_generation.py)、[path_tracking.py](../../host/tankbot_host/path_tracking.py) | [路径报告](NAVIGATION_PATH_TRACKING_VALIDATION.md)；裁判生成路径不等于玩家全局规划课程 |
| 权限 | Weapons C1–C5显示炮弹、隐藏敌车真值；C2/C3授权目标累计RMSE；Navigation C1–C4授权定位RMSE，C4真实追踪误差仅终局 | [关卡YAML](../../levels/README.md)、[04](../04_STATE_AND_VIEW_MODEL.md)、[22](../22_SETTINGS_MODES_AND_PROGRESS.md) | UI指标/图层不自动变为Runtime输入；开发者DTO独立；浏览器本地不是防恶意设备所有者的边界 |
| 算法实验 | 仅Weapons C2的授权输入录制、两版本滤波回放、可选有界诊断、复现导出 | [experiments.py](../../host/tankbot_host/experiments.py)、[weapons.C2.yaml](../../levels/weapons.C2.yaml)、[38](../38_ENGINEERING_AND_ALGORITHM_LAB.md) | [工程报告](ENGINEERING_QUALITY_VALIDATION_20261105.md)；没有通用Lab或控制器成对闭环实验 |
| 项目维护 | 容量分类、完整工程备份、固定revision、清理预览、恢复及中断回滚 | [workspace_maintenance.py](../../host/tankbot_host/workspace_maintenance.py)、[38](../38_ENGINEERING_AND_ALGORITHM_LAB.md) | 工程备份不含个人设置/进度；磁盘清理不等于会话内DeploymentArtifact GC |
| Runtime | 声明总上限20ms；native_local_v1墙钟30ms、browser_pyodide_v1墙钟40ms，均experimental；尝试内冻结、activation+6tick不变；旧batch_budget_ms独用兼容，混用拒绝 | [目录](../../config/runtime-profiles.yaml)、[execution_profiles.py](../../host/tankbot_host/execution_profiles.py)、[robot_graph.py](../../host/tankbot_host/robot_graph.py)、[Supervisor](../../host/tankbot_host/supervisor.py)、[BrowserSupervisor](../../runtime/browser_authority.py)、[桥](../../web/runtime-frame.js)、[ADR-0053](../adr/0053-backend-runtime-execution-profiles.md) | [11月7日报告](RUNTIME_EXECUTION_PROFILES_VALIDATION_20261107.md)：Linux/Firefox、96格81,139批；未证明整局截止失败率<1%，没有逐模块硬CPU隔离 |
| 检查 | tools/check.py统一普通Node、Python、Rust、文档和生成配置检查；WASM与真实网页另分组 | [package.json](../../package.json)、[check.py](../../tools/check.py)、[test_frontend.mjs](../../tools/test_frontend.mjs)、[CI](../../.github/workflows/checks.yml) | CI定义不是远程执行结果；本轮仅做文档适用检查，结果在收尾记录 |

## 冲突与证据缺口

已发现的是现行正文滞后：五/十关、单模块范围、Radar/生命/电机未实现和固定20ms墙钟等说法，与当前实现及后续Accepted ADR不一致。本轮依照已存在的ADR-0043/0046–0053同步说明，不新增架构决策、不更改状态。ADR-0013的完整隔离方案仍为Proposed。

尚无足够证据确认其他OS/浏览器的完整玩家流程、后台/休眠恢复、服务端强沙箱、竞技公平性、独立静态Web存储和低于1%的整局截止失败率；不从CI矩阵、Schema存在或零失败短测推导这些能力。

## 本轮修订对照

| 实际修改文件 | 过时表述 | 当前事实 / 修改范围 | 核对证据 |
| --- | --- | --- | --- |
| [README.md](../../README.md) | 正文仍称20ms墙钟、Navigation仅至C3 | 十一关/C4、冻结profile、C2试点和平台证据分层 | 41、runtime-profiles.yaml、package.json |
| [assets/maps/README.md](../../assets/maps/README.md) | 教学图用途未包含Navigation；旧实测像当前结果 | 补C0–C3实际引用、标注10月28日历史验收 | levels/*.yaml、40 |
| [docs/01_PROJECT_VISION.md](../../docs/01_PROJECT_VISION.md) | 全向/炮台还写为未来，三模式未分状态 | 已实现底盘/武器，Lab试点/Arena计划和首MVP历史分开 | 02、09、38 |
| [docs/02_SYSTEM_ARCHITECTURE.md](../../docs/02_SYSTEM_ARCHITECTURE.md) | 五关、建议目录、前端整体Proposed | 十一关、真实职责/入口、当前Accepted组合及部署限制 | level_plugins.py、scene_definition.py、ADR-0002/0021/0053 |
| [docs/03_PROTOCOL_SPECIFICATION.md](../../docs/03_PROTOCOL_SPECIFICATION.md) | 视图表只列V1–V3，cmd_vel角色和首发视图未分阶段 | V1–V5、速度参考/执行器区别，协商结构与运行状态分开 | authority.py、payloads/envelope Schema、37 |
| [docs/04_STATE_AND_VIEW_MODEL.md](../../docs/04_STATE_AND_VIEW_MODEL.md) | 策略仍Proposed、C1–C4炮弹、除C2外终局才有误差 | 按十一关YAML列UI/程序权限；C2/C3与Navigation实时指标独立 | view.py、campaign.py、各关permissions/evaluation |
| [docs/05_ROBOT_MODULE_SYSTEM.md](../../docs/05_ROBOT_MODULE_SYSTEM.md) | budget_ms当墙钟、M1子集/检查点表述混合 | 声明准入/整批截止/6tick门分离，现有图与目标API分开 | robot_graph.py、execution_profiles.py、runtime/module_runner.py |
| [docs/06_WORKSPACE_AND_TEMPLATES.md](../../docs/06_WORKSPACE_AND_TEMPLATES.md) | 单模块、完整闭环Test及未来GC描述混合 | 现行图/短输入测试、工程备份与会话artifact GC分开 | workspace.py、deployment.py、workspace_maintenance.py |
| [docs/07_SIMULATION_DESIGN.md](../../docs/07_SIMULATION_DESIGN.md) | Radar/生命/电机未实现，5Hz建议像当前，统一RNG仅为设想 | 现有物理/传感器与时钟，实际实例随机流、Replay子集 | 32、33、sensor_instances.py、Core |
| [docs/08_RUNTIME_AND_SECURITY.md](../../docs/08_RUNTIME_AND_SECURITY.md) | 已实现方案与OS隔离目标表混合 | 本机现状/服务端目标分开；历史20ms和当前profile分开 | supervisor.py、browser_authority.py、ADR-0013/0053 |
| [docs/09_LEVEL_DESIGN.md](../../docs/09_LEVEL_DESIGN.md) | 十关、缺C4、工程与进度都独立、完整Lab像现状 | 十一关/路径，独立工程共享存档、试点与未来课程分开 | levels/*.yaml、progression.py、workspace_scope、38/40 |
| [docs/10_DEVELOPMENT_ROADMAP.md](../../docs/10_DEVELOPMENT_ROADMAP.md) | 历史轮次用本轮/当前，20ms及章节链容易误读 | 里程碑开发顺序与玩家解锁分开；注明历史与当前profile | 09、36、40、41及原始报告 |
| [docs/11_CRITICAL_QUESTIONS.md](../../docs/11_CRITICAL_QUESTIONS.md) | RobotApp/scan和资源攻击验证未分目标/实测 | 保留目标答案，标未实现/未验证子项 | 05、08、41 |
| [docs/12_VALIDATION_AND_OPEN_QUESTIONS.md](../../docs/12_VALIDATION_AND_OPEN_QUESTIONS.md) | 十关、M1入口和多个已交付项仍开放 | 统一入口、当前完成/剩余矩阵、M0–M4研究及计数归历史 | tools/check.py、tests、各领域规范与历史报告 |
| [docs/13_PHYSICS_MODEL_DECISIONS.md](../../docs/13_PHYSICS_MODEL_DECISIONS.md) | 原确认尺寸/未来武器可能被当当前参数 | 加历史适用范围和后续模型修订入口，原方程/参数不改 | ADR-0019/0036/0043/0046 |
| [docs/16_BROWSER_RUNTIME.md](../../docs/16_BROWSER_RUNTIME.md) | 正文固定20ms，仅文末补profile | 直接写当前完整解码截止、冻结/旧Worker隔离和实验性40ms | browser_authority.py、runtime-frame.js、41 |
| [docs/17_EDITOR_AND_DEPLOYMENT.md](../../docs/17_EDITOR_AND_DEPLOYMENT.md) | M3单模块/1.5/未做磁盘回收被当当前 | 2.1与现行模块图/维护、scope、短测和会话GC边界 | deployment.py、workspace.py、workspace_maintenance.py |
| [docs/18_CAMPAIGN_DESIGN.md](../../docs/18_CAMPAIGN_DESIGN.md) | 当前1.9、Weapons仅C1–C4弹丸、后续多模块未分 | 2.1模型归属、全Weapons弹丸与C0–C2兼容包装范围 | levels/weapons.C1–C5.yaml、26、32 |
| [docs/22_SETTINGS_MODES_AND_PROGRESS.md](../../docs/22_SETTINGS_MODES_AND_PROGRESS.md) | C1/C2没有真值选项被误解为炮弹也隐藏 | 弹丸与敌车真值分开、UI实时标量和Runtime输入独立 | 关卡YAML、ViewGateway、CampaignSession.public |
| [docs/25_ATTEMPT_RULES_AND_CONFIGURATION.md](../../docs/25_ATTEMPT_RULES_AND_CONFIGURATION.md) | 当前应用2.0、底盘仅几何 | 2.1与完整模型归属；不改时限/伤害/结算参数 | game.yaml、config/chassis、32 |
| [docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md](../../docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md) | 全局章节链、自身定位未来、20ms共享预算 | 双主线、Navigation已实现、Weapons声明准入和墙钟分开 | 36、41、Weapons YAML/robot_graph.py |
| [docs/27_LEVEL_PLUGIN_ARCHITECTURE.md](../../docs/27_LEVEL_PLUGIN_ARCHITECTURE.md) | 五/六/九关及2.0、旧地图/模型能力散落并互相覆盖 | 当前十一关统一加载/场景/规则/权限；原五关审计表独立保留 | level_plugins.py、scene_definition.py、level_rules.py、32/40 |
| [docs/29_CHASSIS_PROFILES.md](../../docs/29_CHASSIS_PROFILES.md) | 完整模型字段仍只列几何，全部正式关卡不启GPS | 补完整字段；Weapons车头GPS与Navigation自身GPS区分 | config/chassis/*.yaml、navigation_sensors.py |
| [docs/31_MAP_OVERRIDE_AND_PREVIEW.md](../../docs/31_MAP_OVERRIDE_AND_PREVIEW.md) | 导航路径生成仍被列为未有 | 裁判路径生成已由C4实现，热切换/自动修复仍未有 | path_generation.py、40 |
| [docs/32_RESOLVED_SCENE_AND_COMPONENTS.md](../../docs/32_RESOLVED_SCENE_AND_COMPONENTS.md) | 原重构范围与当前混合，轮电机仍整体开放 | 原重构/后续Navigation分开；差速电机已实现，剩余扩展明确 | 33、35、40、scene_definition.py |
| [docs/33_NAVIGATION_MOTION_CONTROL.md](../../docs/33_NAVIGATION_MOTION_CONTROL.md) | 后续导航课程全部未实现 | 里程计/EKF/航点/路径已交付，轮胎/电感等仍未有 | 34、35、37、40 |
| [docs/34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md](../../docs/34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md) | 20ms称批次上限 | 两模块声明额度用于准入；墙钟由41规定 | navigation.C1.yaml、execution_profiles.py |
| [docs/35_NAVIGATION_GPS_LOCALIZATION.md](../../docs/35_NAVIGATION_GPS_LOCALIZATION.md) | 总预算含义模糊、路径跟踪未来 | 声明额度与独立墙钟；C3/C4已交付 | navigation.C2.yaml、37、40、41 |
| [docs/37_NAVIGATION_WAYPOINT_CONTROL.md](../../docs/37_NAVIGATION_WAYPOINT_CONTROL.md) | 四模块总20ms未分墙钟 | 20ms是声明准入，整批截止与固定门独立 | navigation.C3.yaml、41 |
| [docs/38_ENGINEERING_AND_ALGORITHM_LAB.md](../../docs/38_ENGINEERING_AND_ALGORITHM_LAB.md) | 收到至提交被写成纯等待 | gate_wait_ms包括门等待/Authority校验，未声称完整分解 | runtime_timing.py、两种Supervisor |
| [docs/40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md](../../docs/40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md) | 当前固定20ms，旧十关未明确时态 | 引用冻结profile；区分初次验收和后续30/40ms证据 | 41、两份路径/Runtime历史报告 |
| [docs/41_RUNTIME_EXECUTION_PROFILES.md](../../docs/41_RUNTIME_EXECUTION_PROFILES.md) | 实现顺序/报告仍用将来时 | 当前实现及既有报告/JSON、本机原始分片与平台限制 | execution_profiles.py、11月7日报告/JSON |
| [docs/README.md](../../docs/README.md) | 日期/基线旧、索引职责和状态不统一 | 2.1/十一关/已提交基线与实验性profile，链接新核对 | HEAD、目录、当前规范及历史报告 |
| [docs/adr/0001-architecture-principles.md](../../docs/adr/0001-architecture-principles.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/0017-confirmed-weapons-loop.md](../../docs/adr/0017-confirmed-weapons-loop.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/0032-weapons-curriculum-and-armor.md](../../docs/adr/0032-weapons-curriculum-and-armor.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/0034-authorized-live-evaluation.md](../../docs/adr/0034-authorized-live-evaluation.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/0047-navigation-odometry-and-control-feedback.md](../../docs/adr/0047-navigation-odometry-and-control-feedback.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/0048-navigation-gps-localization.md](../../docs/adr/0048-navigation-gps-localization.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/0050-estimated-pose-waypoint-control.md](../../docs/adr/0050-estimated-pose-waypoint-control.md) | 原阶段选型/课程/指标/预算容易被当当前 | 仅加现行解读和后续ADR链接；原Context、Decision、参数、计数和Status保持 | ADR索引、0047/0048/0049/0051/0053及相关领域规范 |
| [docs/adr/README.md](../../docs/adr/README.md) | 0051后空行打断表格、旧状态摘要缺局部修订关系 | 修复表格、汇总后续修订；不改状态 | ADR-0049至0053及既有局部修订 |
| [docs/examples/README.md](../../docs/examples/README.md) | M3/M5/通用工厂示意像当前工程，样例目录不全 | 当前分组/历史示意/结构与领域验证分层，覆盖新样例 | docs/examples/*.json、test_protocol_fixtures.py |
| [docs/schemas/README.md](../../docs/schemas/README.md) | M1/1.3和event未实现等当前/历史混写 | 当前版本、22类结构职责与已支持子集；历史演进另列 | docs/schemas/*.json、check_design.py、Host校验 |
| [levels/README.md](../../levels/README.md) | 十关、Nav至C3、诊断仅终局、底盘仅几何 | 十一关、逐项live授权、完整底盘和独立Runtime准入 | 十一份YAML、level_plugins.py、41 |

另外新增本报告，集中记录事实表、修订清单与本轮检查；不新增ADR或游戏功能。AGENTS.md本身已准确描述当前实现，无需再次修改。

## 文档差异与架构冲突处理

未发现本次同步必须通过新决策才能接受的核心职责变化；当前profile、模型、导航任务与双主线均有相应Accepted ADR。文档04曾把Selector发布者写成host:pose_selector，实际 `ViewGateway/PoseSelector` 与Authority生成的是pose_selector；按现有实现修正文案，未改消息/SDK/Schema，也未改变唯一写者原则。动态RobotApp、完整闭环Test、通用RNG/TF和OS资源配额等目标描述已明确为未实现，不能通过改文字冒充落地。

剩余证据缺口包括14个领域夹具中未全部逐项接入的Manifest/策略类描述；相关功能已有独立行为回归，不将其继续统称未实现，也不声称夹具映射已完整。其他OS/浏览器的真实流程、后台/休眠、完整Lab/控制器对照、会话artifact GC和服务端安全仍需后续工作。

## 本轮实际检查与保护结果

- `python3 docs/tools/check_design.py`：退出码0；141份Markdown、1325个本地链接、22份Schema、45个正例、25个结构拒绝例、13个JSON块与17个Python语法块通过。ADR状态仍为51 Accepted / 1 Proposed / 1 Superseded；14个领域案例仅作结构分层检查。
- `python3 tools/export_profile.py --check --offline`：退出码0，生成配置与现有YAML一致，未重新写入夹具。
- `git diff --check`：退出码0。
- `python3 tools/tankbot.py --level-tree --save-file /tmp/tankbot-doc-sync-20261110-no-save/progress.json`：退出码0；显示十一关双主线，新玩家仅c0可挑战。确认该临时目录/存档未创建，不启动仿真或Workspace。
- 对比HEAD的Markdown代码块：JSON/Python内容均未改变；只新增/更新检查命令等文档文字，未修改机器可读夹具。
- 对比ADR：七份加说明的旧ADR的Context、Decision与原状态逐字节保持。
- 对比任务开始SHA-256：44份已有Markdown被修改；代码、YAML/JSON/Schema语义、测试入口及84个已有报告/原始JSON/图片均保持。未操作日常userdata，无提交、推送或重置。

纯文档同步没有重跑npm/全量Python/Rust、WASM、真实网页或长时Runtime矩阵。报告中的81,139批、各课程通关和历史测试计数属于对应旧验收，不属于本轮结果。当前工作区新增的是本报告和文档差异，没有新增游戏实现。
