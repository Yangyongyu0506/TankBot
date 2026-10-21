# Schema 与示例组织

## 目的与状态

本目录提供 `TankBot Protocol 1.0`、Module Contract、Workspace、受信 View Policy 与 ControllerProfile 的结构草案，属于文档产物，尚无 Router、SDK 或游戏实现。Dialect 为 JSON Schema Draft 2020-12；`$id` 中的 `tankbot.example` 是命名占位，不是下载或运行端点。验证工具必须将本地 Schema 注册后离线解析 `$ref`。

| 文件 | 职责 |
| --- | --- |
| [envelope.schema.json](envelope.schema.json) | 公共字段、payload/type/frame 静态组合、请求关联规则 |
| [payloads.schema.json](payloads.schema.json) | 11 个最小负载定义与 Vector3 辅助结构，使用 `$defs`；不单独匹配任意对象 |
| [module-contract.schema.json](module-contract.schema.json) | 端口、周期/event 元数据、预算、依赖与状态版本 |
| [workspace.schema.json](workspace.schema.json) | Manifest、模块引用、连线、精确依赖与位姿来源 |
| [view-policy.schema.json](view-policy.schema.json) | 受信策略字段；不是玩家授权申请格式 |
| [chassis-controller.schema.json](chassis-controller.schema.json) | 受信底盘类型、速度轴限值、cmd_vel_timeout；不是逐条速度消息 |

payload 标识为 `pose2d@1`、`imu@1`、`encoder@1`、`radar@1`、`twist@1`、`view_snapshot@1`、`error@1`、`negotiate_request@1`、`negotiate_response@1`、`runtime_step_request@1`、`runtime_step_result@1`。Twist 保留 linear.x/y/z、angular.x/y/z，二维的 linear.z/angular.x/angular.y 限定为零，底盘是否支持非零 linear.y 由领域层判定。首发 `view_snapshot@1` 的 objects/effects 为空；实体/效果、scan、地图瓦片、pose_fix、fire、选源服务仍须补齐结构和权限后才能注册，不以任意 object 扩展绕过审查。

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

工具检查本地链接、ADR 状态、JSON/Python 片段语法、Schema 定义、完整正例和结构负例；领域负例仅验证“确实通过结构层”，不假装运行尚不存在的 Host 验证器。不导入/执行玩家 Python，不安装依赖、不联网。首次实现后应把这些夹具接入真正的 Router、SDK 和 Adapter 测试。

## 版本、取舍与验收

结构较严格有利于阻止意外真值字段，但新增类型必须版本化注册；扩展字段只走 Envelope 的 `extensions.x_*`。语义约束不硬塞到难维护的 Schema 表达式。更改本目录时同步 [03](../03_PROTOCOL_SPECIFICATION.md)、[05](../05_ROBOT_MODULE_SYSTEM.md)、[06](../06_WORKSPACE_AND_TEMPLATES.md) 和 [样例](../examples/README.md)。

首发冻结前完成所有必需频道与服务的 Schema、授权矩阵及跨语言夹具。当前未实现服务不能因 Schema 存在而标为已完成。
