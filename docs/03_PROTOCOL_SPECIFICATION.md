# 03 TankBot Protocol 初步规范

## 目的、范围与规范状态

本文件定义不依赖 ROS2/DDS 的 `TankBot Protocol 1.0` **未发布草案**。JSON 是首个编码；协议语义不依赖 WebSocket。ADR-0004 接受轻量语义与版本原则，ADR-0005 接受 Transport 抽象；字段和预算仍须通过 M1/M2 夹具与性能验证后冻结。

[ADR-0014](adr/0014-ros-style-velocity-interface.md) 补充约定：消息语义、Topic 命名、单位与坐标系优先参考 ROS 2 习惯；共享习惯不意味着引入 ROS 运行时或声称线协议兼容。连续速度使用 `cmd_vel` Topic，不包装成带起止时间的离散任务。

必须支持身份绑定、权限、可追踪时间、严格负载类型、有界资源与 Replay。初期不做自动节点发现、分布式一致性、任意 QoS 组合或独立 Action 中间件。

## 通信语义

| `message_type` | 语义 | 示例与限制 |
| --- | --- | --- |
| `topic` | 状态、测量或持续更新的设定值；按频道策略保留最新值/历史 | IMU、估计位姿、cmd_vel；无逐条执行确认 |
| `command` | 确有需要的离散操作请求 | 如后续一次开火；需注册独立 Schema 和仲裁，不用于速度流 |
| `service_request` / `service_response` | 有关联 ID、有限时长的请求/响应 | 协商、选定位姿源；不在物理线程阻塞等待 |
| `event` | 已发生的离散事实 | 命令拒绝、模块错误、部署生效；不得隐含秘密坐标 |

Topic 不能因命名为“control”就获得执行器权限。`cmd_vel` 虽是 Topic，仍须经发布授权、单一控制租约、底盘能力/限幅验证与执行器仲裁。耗时测试和部署先使用 `job_id` + 进度事件 + 查询/取消服务；只有出现多个需要统一取消、反馈与恢复语义的长任务，才用新 ADR 引入 Action。

## Envelope

所有传输都保留以下字段，不以运行时对象替代公共语义：

```json
{
  "protocol_version": "1.0",
  "message_type": "topic",
  "channel": "/robot/estimates/odometry/pose",
  "sequence_number": 20,
  "simulation_tick": 120,
  "simulation_time_ns": 2000000000,
  "run_id": "run-demo-001",
  "publisher_id": "module:odometry",
  "request_id": null,
  "frame_id": "map",
  "schema": "pose2d@1",
  "payload": {
    "child_frame_id": "base_link",
    "x_m": 1.2,
    "y_m": 0.4,
    "yaw_rad": 0.1,
    "covariance": [0.04, 0, 0, 0, 0.04, 0, 0, 0, 0.01]
  }
}
```

| 字段 | 约束 |
| --- | --- |
| `protocol_version` | `major.minor`；当前只定义 `1.0` |
| `message_type` / `channel` | 上述枚举；频道必须在注册表，不支持玩家通配订阅 |
| `sequence_number` | 非负安全整数；每 `(run_id, publisher_id, channel)` 单调递增，允许间隙 |
| `simulation_tick` | 消息描述的逻辑时刻；不得用网络接收时间替代 |
| `simulation_time_ns` | `floor(simulation_tick * 1_000_000_000 / physics_hz)`；用整数计算 |
| `run_id` | Authority 分配的不透明纪元，重置/seek 后更换；不是秘密地图种子 |
| `publisher_id` | Authority 绑定的逻辑发布者；不是客户端自报即可信的凭据 |
| `request_id` | command/service 必须为非空字符串，topic/event 为 `null` |
| `frame_id` | 空间数据的参考坐标系；非空间消息为 `null` |
| `schema` | 注册负载标识，如 `pose2d@1`，与频道/type 联合校验 |
| `payload` | 对应 Schema 的对象；禁止未知字段偷偷混入真值 |
| `extensions` | 可选对象，只允许 `x_` 前缀键；无权限和时间语义 |

tick、序号和纳秒计数字段限制在 `0..9007199254740991`，防止 JavaScript 丢精度；测量和协方差的数值可以为负，不受“非负计数”约束。一场运行在计数接近上限前结束并新建纪元。角度用弧度，yaw 标准化到 `[-π, π)`；速度为 `m/s`、角速度为 `rad/s`。JSON 只用 UTF-8，拒绝重复键、非有限数（包括指数溢出）、超深嵌套和尾随内容。

## 坐标、时间与测量语义

平面为右手系：地图 `+x` 向右、`+y` 向上、`+z` 向外；yaw 从 `+x` 绕 `+z` 逆时针为正。`base_link` 的 `+x` 向前、`+y` 向左。Canvas 的屏幕 y 向下只在 Renderer 转换。`world` 是私有物理系，`map` 是任务/玩家地图系，`odom` 是连续但漂移的里程计系；`imu_link`、`radar_link` 是公开标定的刚体传感器系。

`pose2d@1` 表示 envelope `frame_id` 中的 `base_link` 位姿。协方差按 `(x, y, yaw)` 行优先 3×3，单位随分量乘积；`null` 表示未报告不确定度，不能当作零。坐标数值合法不等于坐标系合法：须验证帧注册、允许变换、协方差对称和半正定；容差见 04。

传感器 topic 的 tick 是**采样 tick**，估计 topic 是**被估计状态的 tick**，cmd_vel 是**目标生成上下文 tick**。含延迟的测量可以乱序到达；传输日志另记 `delivery_tick`、`ingress_order`，不改写采样时间。事件使用发生/提交 tick，service 使用其接口定义的逻辑上下文 tick，离散 command 使用生成上下文 tick。时间戳不表示未来预约执行时间；禁止把墙钟放入仿真时间字段。

合法估计输出不得早于执行 profile 的历史窗口，不得晚于执行上下文 tick；初始 `estimate_history_ticks=60`，即允许 `[max(0, activation_tick-60), activation_tick]`。更旧输出报 `STALE_DATA`；窗口内的旧估计保留在调试历史，不能倒退覆盖较新显示。迟到不是“把时间戳改为现在”的理由。细节与统一顺序见 07。

## 频道注册与权限

所有 `/robot/...` 路径均是**当前授权机器人内的虚拟命名空间**；远程连接无法通过路径切换到其他机器人。UI 与 Runtime 是不同主体，系统服务亦不同。

| 频道 | 类型 / Schema | 单一写入者 | 可读者与条件 |
| --- | --- | --- | --- |
| `/robot/sensors/imu` | topic / `imu@1` | Sensor Simulator | 本机器人获授权模块、获准 UI 图层 |
| `/robot/sensors/encoder` | topic / `encoder@1` | Sensor Simulator | 同上 |
| `/robot/sensors/radar` | topic / `radar@1` | Sensor Simulator | 授权模块/UI；标签不是全局实体 ID |
| `/robot/estimates/{module_id}/pose` | topic / `pose2d@1` | 已注册候选模块 | 本机器人、Pose Selector、获准调试 UI |
| `/robot/localization/pose` | topic / `pose2d@1` | Pose Selector | View Gateway、本机器人在策略允许时 |
| `/robot/cmd_vel` | topic / `twist@1` | 当前控制租约持有者 | Chassis Controller / Actuator Arbiter；不转发给对手 |
| `/view/snapshot` | topic / `view_snapshot@1` | View Gateway | 对应玩家 UI |
| `/session/negotiate` | service / 协商 request/response | 连接主体 / Host | 仅本连接 |
| `/runtime/step` | service / RuntimeStep 类型 | Supervisor / 指定 Runtime | 私有运行控制面，不给玩家通用 service 权限 |
| `/system/diagnostics` | event / `error@1` | Host | 对应主体，内容须脱敏 |

`/system/pose` **不是公共频道**。System Pose Provider 在 Authority 私有接口内向 Selector 提供许可候选。`/robot/sensors/pose_fix`、局部 scan、建图瓦片、fire、选源服务等是后续频道，须补 Schema、授权与验收后注册；不能因出现在概念图中就自动开放。

Authority 根据主体、机器人、部署、关卡、频道、操作（publish/subscribe/call）检查 grant；所有资源默认拒绝。每个输出端口拥有单写者租约。重连/部署时旧租约失效；一个 Runtime 内的模块不是彼此隔离的安全主体，模块名只用于配置和路由，不能扩大整个机器人获授的能力。

## 速度 Topic、控制器与离散请求

`/robot/cmd_vel` 使用 `twist@1`，其负载遵循 `Twist` 的 `linear`/`angular` 向量形状：

```json
{
  "linear": {"x": 0.5, "y": 0.0, "z": 0.0},
  "angular": {"x": 0.0, "y": 0.0, "z": 0.2}
}
```

`linear.x=vx` 向前、`linear.y=vy` 向左（m/s），`angular.z=wz` 逆时针（rad/s）；二维场景要求 `linear.z=angular.x=angular.y=0`。Envelope 的 frame 固定为 `base_link`，tick 是生成时刻，`message_type="topic"`、`request_id=null`。通用 Envelope 已承载时间/帧，相当于 stamped 元数据，不在 payload 再复制 Header。消息只表达当前目标速度，不表达计划运动多久。

Host 把有效目标放入内部提交计划；Python 输出仍随 Runtime 批次在固定门提交，外部键盘目标在下一可用门提交。Chassis Controller 消费最新合法目标，并在新消息间保持目标；队列深度为 1，按 `(生成 tick, sequence)` 选择，同源旧时间不能覆盖新目标。序号、run、租约与调度上下文防止旧部署/重放消息重新控制机器人；无逐条速度执行确认。

控制器配置与速度消息分开，配置由受信场景加载并在部署报告中公开，例如：

```json
{
  "controller_profile_version": "1.0",
  "controller_id": "base_controller",
  "drive_model": "differential",
  "command_topic": "/robot/cmd_vel",
  "command_frame": "base_link",
  "cmd_vel_timeout": 0.5,
  "limits": {"max_vx_mps": 3.0, "max_vy_mps": 0.0, "max_wz_radps": 6.0}
}
```

`cmd_vel_timeout` 单位为仿真秒，必须为正。控制器在 `now_tick - target_tick ≥ ceil(cmd_vel_timeout * physics_hz)` 时清空目标并要求零速度；不因晚收到旧消息而刷新其生成时间。以 60 Hz、生成 tick 120、内部提交 tick 126 为例，0.5 s 超时在 tick 150 触发，而非从 126 重新计时。未收到任何目标时保持零目标；主动停车发布零 Twist。实际减速由公开制动/动力学约束决定，不承诺瞬时物理静止。

失去控制租约、断线、reset 或部署切换立即清空旧目标，不等超时；“立即”指下一个权威提交边界，不是异步打断正在积分的物理 tick。无效消息不替换目标、不刷新 watchdog；旧合法目标仅维持到自身超时。手动/自主控制只有一个租约，键盘也必须走该授权入口。Manifest 的模块 config 不能覆盖 Host 的 ControllerProfile 来延长超时或解锁全向能力。

差速模型支持 vx/wz，非零 vy 报 `UNSUPPORTED_MOTION`；未来全向模型可支持 vx/vy/wz，同一 Twist 无需改格式。各轴绝对值不得超过 ControllerProfile 声明的限值，越界拒绝；正常加速度饱和属于物理模型。非零横移不是通过直接改位置模拟，必须由对应底盘模型实现。配置与消息 Schema 可表达未来全向能力不代表该模型已实现。

离散 command/service 的去重键仍为 `(run_id, bound_principal, request_id)`；缓存内相同内容返回已记录结果，同 ID 不同内容报 `DUPLICATE_REQUEST`。窗口为会话内最近 256 项，超出窗口不保证识别重复，不支持自动重试。有副作用服务还须按 artifact/revision/step 等业务键幂等。cmd_vel 不使用此请求缓存，重连也不重发旧速度，需新发布当前意图。

连接先完成 Transport 级认证与角色绑定，再以 `run_id="bootstrap"`、tick/time=0 请求版本协商。选择共同的精确 minor profile，返回真实 `run_id`、`physics_hz` 和能力摘要；请求中的 role 仅为申请。协商前只允许此服务，失败关闭；不公开秘密 seed 或隐藏实体清单。进程内适配也必须显式创建绑定会话。

## 校验、错误与资源上限

入口次序：按预绑定会话 profile 的字节/深度限制 → 严格 JSON 解析 → Envelope 头部字段验证 → 身份/run/sequence → channel/type/schema 注册 → publish/call 权限 → 完整 Envelope/Payload Schema → 数值/时间/帧/业务约束 → 有界提交队列。提供的 Envelope Schema 包含负载引用，可用于完整结构验证；不能因此省略身份与领域验证。订阅和出站也校验权限；服务错误不得暴露未授权对象是否存在。

错误码最少包含 `INVALID_JSON`、`INVALID_SCHEMA`、`NON_FINITE`、`UNAUTHORIZED`、`UNKNOWN_CHANNEL`、`OUT_OF_ORDER`、`WRONG_RUN`、`STALE_DATA`、`INVALID_TIMESTAMP`、`INVALID_FRAME`、`INVALID_COVARIANCE`、`UNSUPPORTED_MOTION`、`MISSED_DEADLINE`、`RATE_LIMITED`、`DUPLICATE_REQUEST`、`VERSION_UNSUPPORTED`。未来时间或与绑定激活上下文不符报 `INVALID_TIMESTAMP`；过期速度报 `STALE_DATA`。`error@1` 使用 `code`、`message`、可空 `field`、可空 `related_request_id`。只传玩家可操作的诊断；详细内部日志不下发。

初始安全 profile：普通 Envelope ≤64 KiB，Runtime 批次 ≤256 KiB，JSON 深度 ≤16；每机器人 ≤256 topic 消息/仿真秒，其中 cmd_vel ≤60/仿真秒；离散 command ≤60/仿真秒，service ≤10/墙钟秒。另有墙钟入口上限 512 消息/秒，防止暂停时灌入。普通 topic 队列每频道最多 32 项，cmd_vel 在各提交门仅保留最新目标；事件/服务/离散命令各 64 项，满时显式拒绝，不能堵住 Core。地图未来分瓦片传输，不通过提高全局限额解决。

状态 topic 可丢最旧项并记录计数；可靠事件/服务在会话存活时有序交付，断线不承诺跨会话重传。断线后重新协商和获取授权快照；执行器进入安全状态。TCP/WebSocket 的顺序不能代替逻辑序号和 run 校验。各预算是待测默认值，变更写入执行 profile 并记录 Replay。

## Transport 接口

```typescript
interface Transport {
  send(message: Envelope): Promise<SendResult>; // 仅确认入有界发送队列
  receive(): AsyncIterable<Envelope>;
  close(reason: string): Promise<void>;
}
// SendResult = { status: "queued" } | { status: "rejected", code: string }
```

`send` 完成不代表命令已执行。Adapter 之外的 Session/Router 执行同一校验。In-Process 使用不可变拷贝和有界队列；Worker 使用 MessagePort 的规范 DTO；WebSocket 一帧一 JSON Envelope；原生 IPC 使用 4 字节大端长度前缀 + UTF-8 JSON（先验长度）；Replay/Test 接收有序记录并注入逻辑到达时刻。WebSocket 认证/Origin 检查与 IPC 端点权限属于 Adapter，不进入 Core。

## Schema、版本与兼容

结构定义见 [Schema 索引](schemas/README.md)，采用 [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)。Schema 不能验证主体权限、PSD、坐标变换或实际截止；必须有领域验证器与负例。

Envelope 核心与 payload `@1` 均禁止未知字段。扩展先放 `extensions.x_*` 并忽略未知键；增加可选频道或功能以 minor 协商，不改变旧 profile。修改单位、字段含义、必填项或现有校验范围必须新 payload 版本，并在无法共存时升级协议 major。禁止“新增必填字段但版本不变”。旧客户端继续选 `1.0`，不得收到只属于新 profile 的 Schema。SDK Version、Protocol Version、Manifest Version、Content Version 分别管理。

2026-10-21 草案修订以 `twist@1` / `/robot/cmd_vel` 替换未发布的旧 drive_command，不作为已发布版本的兼容升级先例；历史决策与理由见 ADR-0014。

## 替代方案、未决项与验收

ROS2/DDS 超出部署和学习负担；直接函数调用只允许在模块内部，不能绕过 Host 权限。二进制编码先等待 profile 显示 JSON 成为瓶颈，届时只替换编码，不改变授权与时间语义。

未决：实际负载预算、地图压缩、断线恢复的历史窗口、首发版本号。验收须包含结构正反例、非法帧/协方差/过期数据、伪造发布者、跨机器人订阅、命令重放、队列溢出、重置旧消息，以及多个 Adapter 对同一夹具产生等价接受结果。
