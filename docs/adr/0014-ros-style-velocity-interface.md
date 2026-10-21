# ADR-0014 ROS 习惯的速度 Topic 与模型无关 Twist

- Status: Accepted
- Date: 2026-10-21
- Scope: 机器人接口惯例、速度目标、底盘适配与失联保护
- Amends: ADR-0004 的 Topic/Command 适用范围、ADR-0010 的控制超时表达；其余决定继续有效

## Context

初版把差速底盘的单个线速度、执行开始和结束 tick 绑定在 `drive_command@1` 中，混合了玩家控制意图、仿真调度与安全看门狗。它也无法自然表达将来的全向底盘横向速度。用户明确要求尽量贴合 ROS 2 的使用习惯，但不引入 ROS2/DDS 运行依赖。

## Decision

1. 将连续速度目标改为 `/robot/cmd_vel` Topic，使用 `twist@1`：`linear` 与 `angular` 各为 `Vector3(x, y, z)`。二维场景使用 `linear.x=vx`、`linear.y=vy`、`angular.z=wz`，其他分量为零；单位、右手坐标系和命名优先参考 ROS 习惯。
2. Payload 仅表示当前目标速度，不携带执行起止时间，也不需要逐条请求 ID 或执行确认。通用 Envelope 保留生成时间与 frame，作为相当于 stamped 消息的元数据；不另外嵌套第二份 Header。
3. 何时进入仿真由可信 Host 确定。Python 批次仍在固定提交门生效；外部输入在下一可用提交门处理。玩家无需计算生效 tick。控制器保持最新有效目标直至收到新目标或自身超时。
4. 超时由可信 ControllerProfile 的 `cmd_vel_timeout`（仿真秒）配置，以目标生成时间判断新鲜度；不是每条消息的有效期字段。失去租约、断线、reset 或部署切换立即清空目标。超时后的目标是零速度，实际停车服从公开动力学与制动限制。
5. Chassis Controller 把 Twist 转换为底盘可实现的运动。差速模型只支持 vx/wz，非零 vy 显式拒绝并诊断；全向模型未来可支持 vx/vy/wz，不能在差速模型中偷偷横移。本次只设计扩展接口，不实现全向轮或额外传感器。
6. Topic 承载连续设定值；Service 承载有限请求响应；Action 是否引入仍按实际长任务需求决策。自定义 `command` 仅保留给确有必要的离散操作，不作为执行器的唯一入口。所有入口仍执行权限、控制租约、资源配额和物理仲裁。
7. 后续接口优先参考 ROS 的消息语义、命名、单位与坐标系；目前自定义 Pose2D/IMU 等不是完整 ROS 消息，逐项评审后演进，不宣称网络或 SDK 与 ROS 2 直接兼容。

## Alternatives

- 保留起止 tick：适合轨迹点/预约任务，但给速度流增加不必要的计划责任；需要轨迹控制时单独设计 trajectory 接口。
- 扁平 `vx/vy/wz`：二维简洁，但与 `Twist.linear/angular` 习惯不同；采用熟悉的 Vector3，二维无效轴显式为零。
- 无限保持最后速度：失联危险；逐条 TTL：污染控制意图。采用控制器统一 watchdog。
- 直接依赖 ROS2/DDS：超出跨平台部署边界；只参考公开惯例。

## Consequences / Constraints

相同控制算法接口可服务不同底盘；发布者持续输出最新目标即可。增加少量零值字段，换取更熟悉的数据形状。底盘能力、限速、看门狗与调度均是 Host 配置，不能由消息自行提权。对差速横移的严格拒绝是 TankBot 的教学/验证选择，不宣称所有 ROS 控制器也如此处理。

协议 1.0 尚未发布，因此以新的 `twist@1` 和频道替换旧草案，不保留虚假兼容层。已发布后若再改公共含义，仍遵守协议版本规则。本 ADR 接受接口方向，不代表 SDK、控制器或全向模型已经实现。

## References / Open Questions

参考定义：[Twist](https://docs.ros.org/en/rolling/p/geometry_msgs/msg/Twist.html)、[ROS 2 官方 Twist 源码](https://github.com/ros2/common_interfaces/blob/rolling/geometry_msgs/msg/Twist.msg)、[diff_drive_controller](https://control.ros.org/rolling/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html)、[mecanum_drive_controller](https://control.ros.org/rolling/doc/ros2_controllers/mecanum_drive_controller/doc/userdoc.html)。本轮浏览工具连接失败，官方站点与源码直连也超时，未完成在线复核；不引用未经核实的 rolling 版本参数默认值。TankBot 建议的 0.5 s 超时仍须通过控制与失联测试确定。

## Acceptance Criteria

Schema 接受 vx/vy/wz 形状，拒绝旧起止字段与非平面轴；SDK 示例无底层调度字段。未来 Host 测试覆盖最新值替换、旧消息不覆盖新目标、按生成时间超时、租约撤回、差速拒绝 vy、全向适配不改公共消息，以及录制重放。设计与夹具见 [03](../03_PROTOCOL_SPECIFICATION.md)、[07](../07_SIMULATION_DESIGN.md)、[Schema 索引](../schemas/README.md)。
