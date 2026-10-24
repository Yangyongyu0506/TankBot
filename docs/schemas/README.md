# Schema 与示例组织

## 目的与状态

本目录提供 `TankBot Protocol 1.0`、Module Contract、Workspace、受信 View Policy、ControllerProfile 及 M1 SimulationProfile 的结构定义。M1 Host/SDK 已使用其中的周期轮组/IMU/位姿接口；其他 Schema 仍是后续设计。Dialect 为 JSON Schema Draft 2020-12；`$id` 中的 `tankbot.example` 是命名占位，不是下载或运行端点。验证工具必须将本地 Schema 注册后离线解析 `$ref`。

| 文件 | 职责 |
| --- | --- |
| [envelope.schema.json](envelope.schema.json) | 公共字段、payload/type/frame 静态组合、请求关联规则 |
| [payloads.schema.json](payloads.schema.json) | 协议负载与 Vector3/FireResult 辅助结构，使用 `$defs`；不单独匹配任意对象 |
| [module-contract.schema.json](module-contract.schema.json) | 端口、周期/event 元数据、预算、依赖与状态版本 |
| [workspace.schema.json](workspace.schema.json) | Manifest、模块引用、连线、精确依赖与位姿来源 |
| [view-policy.schema.json](view-policy.schema.json) | 受信策略字段；不是玩家授权申请格式 |
| [chassis-controller.schema.json](chassis-controller.schema.json) | 受信底盘类型、速度轴限值、cmd_vel_timeout；不是逐条速度消息 |
| [wheel-calibration.schema.json](wheel-calibration.schema.json) | radial_omni@1 公开轮组标定和可复用几何结构 |
| [simulation-profile.schema.json](simulation-profile.schema.json) | M1 唯一配置文件的必填结构，跨字段/数值可行性另由 Host/Core 校验 |
| [campaign.schema.json](campaign.schema.json) | M4 受信关卡、Radar、巡逻与血量配置；由单文件配置引用 |

payload 标识为 `joint_state@1`、`pose2d@1`、`imu@1`、`encoder@1`、`radar@1`、`twist@1`、`view_snapshot@1`、`error@1`、`negotiate_request@1`、`negotiate_response@1`、`runtime_step_request@1`、`runtime_step_result@1`。Twist 保留 linear.x/y/z、angular.x/y/z，二维的 linear.z/angular.x/angular.y 限定为零，底盘是否支持非零 linear.y 由领域层判定。首发 `view_snapshot@1` 的 objects/effects 为空；实体/效果、scan、地图瓦片、pose_fix、选源服务仍须补齐结构和权限后才能注册，不以任意 object 扩展绕过审查。

## 四层验证职责

1. 严格 JSON/Schema：重复键、结构、字段、类型、枚举、静态上下界；非有限数字在 JSON 解析/数值层拒绝。
2. 数值/时序：PSD、物理范围、时间公式、run、未来/过期、周期与 deadline 的跨字段关系。
3. 帧与业务：帧注册/变换许可、端口存在、依赖图、选源与策略窗口。
4. 权限：绑定身份、部署租约、机器人范围、关卡 grant、频道操作和输出额度。

Schema 通过不表示消息可信。`validation-cases.json` 特意包含 **Schema 应通过但将由未来领域验证器拒绝** 的案例，防止把安全语义误归给 Schema。

## 运行文档检查

在已具备 `jsonschema`（支持 2020-12）和 `referencing` 的 Python 环境执行：

```bash
python3 docs/tools/check_design.py
```

工具检查本地链接、ADR 状态、JSON/Python 片段语法、Schema 定义、完整正例和结构负例；领域负例仅验证“确实通过结构层”，不代替真实 Host 验证。不导入/执行玩家 Python，不安装依赖、不联网。M1 已在 tests/test_protocol_fixtures.py 接入其中 10 个协议领域拒绝案例，另由 tests/test_m1.py 覆盖物理/进程/视图。Manifest/event 等剩余案例仍为后续实施，不能混算。

## 版本、取舍与验收

结构较严格有利于阻止意外真值字段，但新增类型必须版本化注册；扩展字段只走 Envelope 的 `extensions.x_*`。语义约束不硬塞到难维护的 Schema 表达式。更改本目录时同步 [03](../03_PROTOCOL_SPECIFICATION.md)、[05](../05_ROBOT_MODULE_SYSTEM.md)、[06](../06_WORKSPACE_AND_TEMPLATES.md) 和 [样例](../examples/README.md)。

首发冻结前完成所有必需频道与服务的 Schema、授权矩阵及跨语言夹具。当前未实现服务不能因 Schema 存在而标为已完成。

## M1b 增量

已注册 turret_velocity@1、fire_command@1、weapon_state@1、view_snapshot@2，接口权威见 [14](../14_WEAPONS_DESIGN.md)。旧 view_snapshot@1 的空实体数组约束不变；@2 只允许严格 projectile/target 联合类型，effects 仍为空。结构夹具同时覆盖空开火 payload、请求类型/帧、反馈脱敏及旧快照不能夹带实体。SimulationProfile 内部版本为 1.1，weapons/control_sources/practice_view_policy 均为必填；Model/权限跨字段约束仍由 Host/Core 验证。

## 显示配置增量

SimulationProfile 内部版本升为 1.2，新增必填 rendering：显示缓冲、相机、网格及 differential/omnidirectional 独立外观。Host 另检查历史长度覆盖插值延迟与快照周期；协议 Envelope / view_snapshot@1/@2 形状未变。具体字段/语义见 [15](../15_RENDERING_DESIGN.md)，不将显示配置用于修改物理状态。

## 全向轮组修订

当前 SimulationProfile 为 1.3，wheels.omnidirectional 显式声明 radial_omni@1、center_radius_m 和四组 name/azimuth_deg；移除旧麦轮几何字段。公开 wheel_calibration 添加共同 radius_m，结构由 wheel-calibration.schema.json 验证，90° 等距/唯一命名另由 Host/Core 验证。协议 JointState/Twist 结构、单位与权限不变，旧配置和物理回放不能忽略模型版本；参见 [ADR-0019](../adr/0019-fourfold-omni-wheel-layout.md)。

## M2 配置增量

内部 SimulationProfile 版本 1.4 必填 browser 段（资源 origin 端口、独立初始化预算、UI 待处理控制请求上限与显式 QA 开关）；物理/SDK/协议消息未变。旧 1.3 文件须显式迁移，工具不覆盖。49 个 Envelope 夹具已接入真实多 Adapter 及浏览器同源验证器，见 16 与 M2 报告；M3 已实现单模块 Manifest profile；event/完整模块图仍未实现。

M3 内部 SimulationProfile 为 **1.5**，新增必填 workspace 限额；未改变已确认物理或 Protocol 1.0。实际单模块夹具为 `m3-workspace.json` 与 `m3-module-contract.json`，通用 `tankbot.json` / `module-contract-event.json` 保留为未来图组装示例，不能混用为当前可运行项目。

M4 内部配置为 **1.6**，增加必填 campaign；1.5 沙盒仍可读。新增 `target_estimate@1` 的地图点/可空 2×2 协方差、`view_snapshot@3` 的严格目标估计 Envelope，以及受信策略的 `target_estimates_allowed`。旧快照结构保留，PSD、历史时间、权限与重复采样计分仍由领域层执行。动态目标的 motion/health 仅在已确认教学场景启用；详细语义见 [18](../18_CAMPAIGN_DESIGN.md)。
