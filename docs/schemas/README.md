# Schema与结构验证

## 当前版本与已支持范围

应用配置为 `config_version: 2.1`，课程源 `schema_version: 1.0`，完整底盘profile为2.0，运行profile目录为1.0；Protocol 1.0和SDK 0.1.0仍是未发布的仓库profile。版本属于不同接口，不能一起升级或由旧报告推断。当前十三关、模块图、编辑部署、设置/进度、C2实验与工程备份已使用相应Schema；字段语义和平台证据以领域规范为准。

所有Schema使用JSON Schema Draft 2020-12；`tankbot.example`的$id只是命名标识，离线注册本地引用，不是下载地址。源YAML先安全解析/引用展开，再验证生成的内部配置；Schema合法不代表获得权限、算法正确或平台已支持。

## 一次性规划准备（C5）

[global-planning.schema.json](global-planning.schema.json)定义参数、准备声明和私有已解析任务结构；[preparation-task.schema.json](preparation-task.schema.json)定义plan/initialize请求与响应，版本1.0。workspace Manifest新增可选preparation声明，由同一关卡配置派生，旧Manifest形状仍合法。level支持global_planning规则、occupancy_grid/planning_goal输入授权、独立规划图层及live/terminal标量；simulation-profile允许已解析任务。结构验证不代替5秒截止、身份匹配、原始地图栅格语义、保守膨胀或整段路径安全校验，见 [42](../42_NAVIGATION_GLOBAL_PLANNING.md)。

## 文件与职责

| Schema | 当前职责 |
| --- | --- |
| [envelope](envelope.schema.json) | 公共Envelope、消息类型/帧静态组合与关联 |
| [payloads](payloads.schema.json) | 已登记负载的$defs；不能用任意object绕过类型注册 |
| [module-contract](module-contract.schema.json) | 输入输出、periodic/event、声明预算、依赖和状态版本 |
| [workspace](workspace.schema.json) | Manifest、模块/连线、依赖与位姿源；动态build_robot仍非运行API |
| [view-policy](view-policy.schema.json) | 受信显示策略结构，不是玩家提权请求 |
| [chassis-controller](chassis-controller.schema.json) | 底盘速度能力、限制和watchdog，不是每条指令 |
| [wheel-calibration](wheel-calibration.schema.json) | radial_omni@1公开轮组几何；差速几何由完整底盘Schema约束 |
| [chassis-profile](chassis-profile.schema.json) | 完整底盘的质量/惯量、轮组、伺服/阻力、控制器、装甲/安装和外观；可选差速motor |
| [simulation-profile](simulation-profile.schema.json) | 已解析应用配置与兼容Core/Authority DTO；引用和数值可行性另验 |
| [campaign](campaign.schema.json) | 生成的课程兼容DTO及既有目标/生命/传感器组件，不是第二套源配置 |
| [level](level.schema.json) | 独立YAML：元数据、世界/实例、接口/权限、任务/诊断、教材与脚手架 |
| [path-tracking](path-tracking.schema.json) | 生成器、任务和已解析参考的JSON表示；安全性/摘要另验 |
| [settings](settings.schema.json) / [progress](progress.schema.json) | 本机YAML设置与版本1进度；前置闭包/解锁由目录解释 |
| [gamepad-input](gamepad-input.schema.json) | 映射、死区、速度和发送周期，不授予执行器权限 |
| [player-dependencies](player-dependencies.schema.json) | 课程库白名单，导入与运行检查由SDK/Host执行 |
| [engineering](engineering.schema.json) | 实验、诊断、备份/恢复等工程配额 |
| [experiment](experiment.schema.json) / [experiment-package](experiment-package.schema.json) | 授权输入记录与比较/失败导出包，不含私有目标参考 |
| [workspace-backup](workspace-backup.schema.json) | 工程备份结构，摘要/引用/CAS/安全路径及实际配额由Store验证 |
| [runtime-execution](runtime-execution.schema.json) | 可信后端目录、共同声明上限、独立整批墙钟和版本/状态 |
| [runtime-benchmark](runtime-benchmark.schema.json) | 隔离基准候选、工作负载/校准、样本与磁盘限额 |

## 消息、配置与运行能力的区别

现用负载覆盖Pose2D、JointState/Encoder/IMU、Radar、目标点/位姿/极坐标、匿名装甲、Twist、轮电压、炮台速度/角加速度、开火及武器反馈。Navigation GPS为position_fix2d@1，公开目标为waypoint_goal@1；完整路径一次通过受权初始化配置交付，不新增路径Topic。各canonical频道及兼容规则见 [03](../03_PROTOCOL_SPECIFICATION.md)。

view_snapshot@1保留空objects/effects；@2增加获授权弹丸/目标，@3增加目标估计，@4增加图输出，@5增加白名单自身位姿候选。旧版本结构不自动接受新字段，当前Web已解码这些版本；图层、候选与指标仍分别授权，见 [04](../04_STATE_AND_VIEW_MODEL.md)。

negotiate等结构夹具不证明正式远程会话服务已发布；地图瓦片、通用动态TF/选源服务、任意异步融合仍未实现。intercepted_gps兼容组件存在，但当前正式Weapons不启用；不能由Schema枚举推断某关开放该数据。

runtime.profiles_file只存在于可信YAML引用阶段，解析后为runtime.profiles；与旧batch_budget_ms互斥。旧字段独用时准入/墙钟仍同值。共同声明上限不等于墙钟，timing.budget_ms只保留为墙钟诊断别名；数值、冻结与后端选择以 [41](../41_RUNTIME_EXECUTION_PROFILES.md) 为准。

## 四层验证职责

1. 安全解析/结构：文件大小、重复键、对象标签、字段/类型/枚举和静态范围；JSON不接受非有限数字。
2. 数值/时序：PSD、真实周期关系、run、未来/过期、采样/提交与截止；不借真值替玩家修复估计。
3. 帧与业务：帧关系、机器人/实例归属、端口/依赖、路径安全/摘要、前置未知和循环。
4. 权限：可信身份/部署、关卡grants、Topic操作、参考与执行器仲裁、View Policy和资源额度。

validation-cases.json刻意包含Schema应通过的领域负例。文档工具只确认其不被结构层提前拒绝；test_protocol_fixtures.py直接执行其中10个协议领域案例。模块图、策略和Workspace另有行为测试，但不能据此声称所有文档案例都已逐项映射，也不能再把这些功能整体标为未来实现。

## 检查入口与限制

```bash
python3 docs/tools/check_design.py
python3 tools/export_profile.py --check --offline
```

需要已准备的requirements.txt依赖。前者离线核对本地链接、ADR、Schema、正/反结构夹具、JSON/Python片段语法和课程引用；后者核对从YAML生成的Rust/Node夹具。二者不运行完整玩家流程或证明安全隔离。完整标准入口为tools/check.py，WASM和真实网页分组见 [38](../38_ENGINEERING_AND_ALGORITHM_LAB.md)。

公共结构变化须同步领域规范、SDK/协议映射、样例和语义回归，不只让Schema通过。当前源码和报告的区别见 [本轮核对](../reports/DOCUMENTATION_STATE_SYNC_20261110.md)。

## 历史版本演进（不作为当前默认）

| 阶段 | 当时配置与主要增量 |
| --- | --- |
| M1b | 1.1增加武器/控制源与严格view_snapshot@2 |
| 显示与全向修订 | 1.2引入rendering，1.3改为radial_omni@1几何 |
| M2 / M3 | 1.4引入browser；1.5增加workspace，原验收仅单模块 |
| M4 | 1.6增加campaign、目标估计和view_snapshot@3；设置/存档、手柄与库策略随后扩展 |
| 插件与底盘 | 独立关卡、几何资产后扩展为2.1完整底盘/实例/场景；旧形状作为显式兼容DTO |
| Navigation与工程 | 追加轮电压、GPS/候选对照、航点、路径与工程Schema；未重定义旧消息 |
| 后端profile | 在2.1配置内拆分准入/墙钟，旧单字段独立模式仍兼容，见ADR-0053 |

各阶段原始验收计数、配置和失败保留在reports，不将旧20ms或旧单模块范围作为当前限制。C5新增原始地图/一次性规划准备合同，见42；scan增量见43；未来SLAM、多机器人与远程沙箱仍须独立设计和验证。

## C6扫描与局部导航

`local-navigation.schema.json`约束私有静态障碍生成参数与输入年龄；`level.schema.json`注册distance_scan、局部适配器、扫描显示及指令曲线。payloads/envelope注册scan2d@1与local_control_feedback@1，SDK/Authority补等长、量程、原采样tick等语义检查。simulation-profile仅内部保存private_obstacles；普通启动/管理投影不得包含它。参数和验收见 [43](../43_NAVIGATION_LOCAL_AVOIDANCE.md)。
