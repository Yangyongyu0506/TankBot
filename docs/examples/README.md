# 接口样例与验证夹具

## 目的与范围

这里是可机读的设计/验证样例；实际 M1 多文件机器人例子在根 examples/robot，不把这些夹具当作运行部署或关卡。`run-demo-001`、主体 ID、profile 与 SDK `0.1.0` 均为示例值，不代表真实服务器或已发布 SDK。

| 文件 | 用途 |
| --- | --- |
| [pose-message.json](pose-message.json) | odometry 候选位姿，tick 120 / 2 s |
| [imu-message.json](imu-message.json)、[encoder-message.json](encoder-message.json)、[radar-message.json](radar-message.json) | 类型化测量 |
| [omni-wheel-calibration.json](omni-wheel-calibration.json) | 当前固定全向轮 radial_omni@1 公开标定，R=0.25 m/r=0.10 m |
| [joint-state-message.json](joint-state-message.json) | M1 按轮名的编码器角/角速度观测 |
| [cmd-vel-message.json](cmd-vel-message.json) | tick 120 生成的车体 Twist Topic，没有执行起止字段 |
| [cmd-vel-omni-message.json](cmd-vel-omni-message.json) | 非零 linear.y 的结构正例；当前全向轮底盘已实现该能力 |
| [chassis-controller.json](chassis-controller.json) | 差速底盘与 0.5 s cmd_vel_timeout 的受信配置 |
| [turret-velocity-message.json](turret-velocity-message.json)、[fire-command.json](fire-command.json)、[weapon-state-message.json](weapon-state-message.json) | M1b 炮台速度、幂等单发与自身反馈 |
| [weapons-practice-view.json](weapons-practice-view.json) | 显式真值练习的严格 view_snapshot@2 |
| [view-snapshot.json](view-snapshot.json) | tick 126 的授权估计视图，不含完整世界 |
| [negotiate-request.json](negotiate-request.json)、[negotiate-response.json](negotiate-response.json) | bootstrap 协商 |
| [runtime-step-request.json](runtime-step-request.json)、[runtime-step-result.json](runtime-step-result.json) | tick 6 激活、tick 12 提交的私有 Runtime 控制面 |
| [error-event.json](error-event.json) | 脱敏错误事件 |
| [module-contract.json](module-contract.json)、[module-contract-event.json](module-contract-event.json) | periodic / event 两种 Contract |
| [tankbot.json](tankbot.json) | Workspace Manifest 与端口连接 |
| [view-policy.json](view-policy.json) | 禁用系统源的受信策略 |
| [validation-cases.json](validation-cases.json) | 对正例作单点修改的结构/领域负例计划 |

## 约束与验收

频道均为当前授权机器人的虚拟路径。文件中的 `publisher_id` 不提供权限，实际连接必须由 Authority 绑定。速度样例在 Host 内部若于 tick 126 提交，按生成 tick 120 和配置的 0.5 s 超时将在 tick 150 失效；这些时刻不由玩家写入 payload。

`validation-cases.json` 使用 `mutation` 表示单次修改，`mutations` 数组表示按顺序修改多处（空数组表示只改变测试上下文）；pointer 使用 JSON Pointer。`context` 给出控制器当前 tick、底盘能力或上一个目标等假设，属于未来测试装置，不会成为线上消息。`layer="schema"` 必须结构拒绝，`layer="domain"` 应结构通过但未来 Host 拒绝；后者不算已完成语义测试。未用结构验证器假装测试 watchdog 或真实全向运动。

示例与正文变更应一起提交。检查命令见 [Schema 说明](../schemas/README.md)；完整语义与时间规则见 [03](../03_PROTOCOL_SPECIFICATION.md)、[07](../07_SIMULATION_DESIGN.md)。
