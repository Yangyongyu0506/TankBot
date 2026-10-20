# 接口样例与验证夹具

## 目的与范围

这里是可机读的设计样例，不是运行部署或关卡内容。`run-demo-001`、主体 ID、profile 与 SDK `0.1.0` 均为示例值，不代表真实服务器或已发布 SDK。

| 文件 | 用途 |
| --- | --- |
| [pose-message.json](pose-message.json) | odometry 候选位姿，tick 120 / 2 s |
| [imu-message.json](imu-message.json)、[encoder-message.json](encoder-message.json)、[radar-message.json](radar-message.json) | 类型化测量 |
| [drive-command.json](drive-command.json) | tick 120 生成，tick 126 执行，tick 138 失效 |
| [view-snapshot.json](view-snapshot.json) | tick 126 的授权估计视图，不含完整世界 |
| [negotiate-request.json](negotiate-request.json)、[negotiate-response.json](negotiate-response.json) | bootstrap 协商 |
| [runtime-step-request.json](runtime-step-request.json)、[runtime-step-result.json](runtime-step-result.json) | tick 6 激活、tick 12 提交的私有 Runtime 控制面 |
| [error-event.json](error-event.json) | 脱敏错误事件 |
| [module-contract.json](module-contract.json)、[module-contract-event.json](module-contract-event.json) | periodic / event 两种 Contract |
| [tankbot.json](tankbot.json) | Workspace Manifest 与端口连接 |
| [view-policy.json](view-policy.json) | 禁用系统源的受信策略 |
| [validation-cases.json](validation-cases.json) | 对正例作单点修改的结构/领域负例计划 |

## 约束与验收

频道均为当前授权机器人的虚拟路径。文件中的 `publisher_id` 不提供权限，实际连接必须由 Authority 绑定。`validation-cases.json` 的 `mutation.pointer` 使用 JSON Pointer，`layer="schema"` 必须结构拒绝，`layer="domain"` 应结构通过但未来 Host 拒绝；后者不算已完成语义测试。其上下文假设写在 note 字段，不能当独立无上下文的网络消息。

示例与正文变更应一起提交。检查命令见 [Schema 说明](../schemas/README.md)；完整语义与时间规则见 [03](../03_PROTOCOL_SPECIFICATION.md)、[07](../07_SIMULATION_DESIGN.md)。
