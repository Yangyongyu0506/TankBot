# 05 Robot Module Contract 与 Python SDK

## 目的、范围与约束

`tankbot` SDK 隐藏 JSON、网络、进程和权限细节，公开稳定的类型、模块生命周期和端口。初学者函数与高级模块采用同一份 Contract 及同一 Host 验证路径。ADR-0008 接受 Contract 和混合交互原则；当前已实现类型化消息、同步periodic/event、声明式模块图与课程适配器，源码在 `sdk/python/tankbot/` 和runtime；尚未发布到pip。下文区分现有API、历史M1子集和未实现扩展。

## 类型与 Contract

SDK 核心类型是不可变值：`Pose2D`、`ImuData`、`EncoderData`、`RadarData`、`Vector3`、`Twist`、`Sample[T]`、`Inputs`、`ModuleContext`、`Module`。编码映射以 03 和 Schema 为准：`Pose2D(x_m, y_m, yaw_rad, covariance, child_frame_id="base_link")`；`EncoderData(left_distance_m, right_distance_m)` 为自本 run 重置以来的累计轮距；`ImuData(angular_velocity_z_radps, linear_acceleration_x_mps2, linear_acceleration_y_mps2)`；`Sample` 包含 `data`、`simulation_tick`、`frame_id`、`sequence_number`。SDK 解码时保留时间与帧，不只传数值。

`Vector3(x=0.0, y=0.0, z=0.0)` 与 `Twist(linear: Vector3, angular: Vector3)` 参考 ROS 的熟悉形状，`Twist()` 默认为两个零向量，序列化总是给出全部分量。二维使用 linear.x/y 与 angular.z，其他轴显式为零；时间和 frame 由 Sample/Envelope 承载，不加入消息执行起止字段。现有 EncoderData 是差速左右轮接口，并非所有底盘通用；M1 新增独立 `JointState(name, position, velocity, effort=())`，数组为不可变 tuple，单位 rad/rad·s⁻¹，频道 `/robot/sensors/joint_states`；差速/径向全向轮共用该新 Contract。不能伪造左右轮数据或悄悄改变 encoder@1 含义。

每个模块提供可静态检查的 `contracts/<module_id>.json`：

```json
{
  "contract_version": "1.0",
  "module_id": "odometry",
  "entry_point": "localization.odometry:Odometry",
  "inputs": {
    "encoder": {"schema": "encoder@1", "required": true, "max_age_ticks": 12},
    "imu": {"schema": "imu@1", "required": false, "max_age_ticks": 6}
  },
  "outputs": {"pose": {"schema": "pose2d@1"}},
  "execution": {
    "mode": "periodic",
    "period_ticks": 6,
    "deadline_ticks": 6,
    "budget_ms": 20
  },
  "dependencies": [],
  "state_version": "1"
}
```

`module_id` 为小写 snake_case，在部署内唯一。Contract 声明端口类型、必要输入、新鲜度、执行频率/触发、预算、初始化依赖、状态版本；Manifest 只负责把端口接到频道。Host 以 Contract、任务 grant、运行 profile 三者交集配置执行，玩家修改文件不能提高配额或授予权限。

Contract的 `execution.budget_ms` 是模块声明额度，用于模块图准入和诊断，不是Supervisor单独为该模块强制的墙钟截止。Host检查整图声明总和不超过冻结profile的 `module_declared_budget_cap_ms`；整批往返另受 `batch_wall_deadline_ms` 约束。当前目录、后端选择、新旧配置互斥与公开摘要以 [41](41_RUNTIME_EXECUTION_PROFILES.md) 为准。`dependencies` 只规定setup顺序，必须为无环图；Topic反馈环合法，但跨模块边至少延迟到下一次输入快照，不能同回调递归执行。

## Module API 与生命周期

```python
from typing import cast
from tankbot import Module, ModuleContext, Inputs, Pose2D, EncoderData, ImuData, Sample

class Odometry(Module):
    def setup(self, ctx: ModuleContext) -> None:
        self.previous_encoder: EncoderData | None = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        encoder: Sample[EncoderData] | None = cast("Sample[EncoderData] | None", inputs.latest("encoder"))
        imu: Sample[ImuData] | None = cast("Sample[ImuData] | None", inputs.latest("imu"))
        # TODO: 用测量、ctx.dt_seconds 和自己的状态计算 estimate: Pose2D。
        # 完成算法后：ctx.publish("pose", estimate, frame_id="map",
        #                         simulation_tick=encoder.simulation_tick)
        raise NotImplementedError

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.previous_encoder: EncoderData | None = None

    def teardown(self, ctx: ModuleContext) -> None:
        pass
```

上面是模板示例；M1 可执行多文件里程计见 `examples/robot/localization/`。完整目标 `ModuleContext` 拟公开 `simulation_tick`、`dt_seconds`、`output_commit_tick`、不可变 `config`、按模块派生的 `rng`、有配额的 `log` 和 `state` 检查点接口。它没有 World、物理对象、宿主文件系统、真实地图 seed 或未授权变换。

`ctx.publish(port, value, frame_id, simulation_tick=None)` 在本激活批次收集输出，默认 tick 为激活 tick；候选频道与 publisher 由已验证连接绑定。返回不代表已提交。输入是快照，模块不能修改 Router 缓存。`Inputs.latest(port)` 在允许的历史内选 `(sample_tick, sequence)` 最大的合法样本；过期可选输入返回 `None`。

控制模块声明输出端口 `cmd_vel: twist@1`，由 Manifest 连接 `controller.cmd_vel → /robot/cmd_vel`。在 `Module.update` 内的示例为：

```python
from tankbot import Twist, Vector3

velocity: Twist = Twist(
    linear=Vector3(x=0.5, y=0.0, z=0.0),
    angular=Vector3(x=0.0, y=0.0, z=0.2),
)
ctx.publish("cmd_vel", velocity, frame_id="base_link")
```

当前全向轮底盘支持非零 `linear.y`，差速底盘只接受零横向分量。Publisher 自动绑定生成 tick；算法无需使用 `output_commit_tick` 填写执行计划，该上下文字段仅供时延诊断/高级补偿。统一看门狗位于控制器配置，玩家发布零 Twist 可主动停车，停止发布则按配置超时。

生命周期为 `created → initializing → ready → running → stopped`；异常可进入 `faulted`。部署时先按依赖调用 `setup`，成功后才能激活。新 run 在 tick 0 调用 `reset` 清空时间相关状态、输入历史和 RNG。调度起点 `origin_tick` 是部署生效 tick，run 重置时归零；第一个周期回调在 `origin_tick + period_ticks`，因此正常 `dt_seconds > 0`。`teardown` 有界且尽力执行，强杀时不保证运行。

模块对象字段只活在当前 Runtime。持久检查点是未实现的目标设计：未来可选ctx.state.get/set须保存带state_version的有界JSON，写隔离数据区并由Host校验；不得pickle任意对象。默认部署不继承旧内存或检查点，跨代码版本恢复需显式迁移并测试。

## 调度与错误语义

| 模式 | 首发语义 | 约束 |
| --- | --- | --- |
| 同步 periodic | tick 为周期整数倍时激活，单回调不重入 | 默认模式；取该 tick 的冻结输入快照 |
| 同步 event | 指定输入有新样本时，下个可用 tick 激活 | Contract 为 `mode="event"`、`trigger_inputs`、`min_interval_ticks`；同 tick 合并事件 |
| 异步 callback | 后续研究 | v1 不接受 `async def update`，避免墙钟 await 改变仿真含义 |

周期与event使用同一声明准入及固定提交机制；event的最小间隔至少等于deadline，periodic的period也必须不小于deadline。同机器人模块的 `deadline_ticks` 必须等于 `runtime.commit_delay_ticks`，当前为6，才能共享批次生效tick；不支持的配置在准入时拒绝。这个仿真时间边界与后端墙钟截止是两道独立条件，增加墙钟时限不能移动提交门。

`dt_seconds` 是距上次**实际调用的激活时刻**的 tick 差/physics_hz，首次从 `origin_tick` 算起；缺输入/忙碌跳过没有调用，因此下次 dt 累积。回调异常或输出被拒绝不会回滚任意 Python 对象字段，下次 dt 仍从该次调用算，玩家需修复/显式重置状态。`ctx.dt_seconds` 不是传感器采样时间差，算法应使用 Sample 的 tick 处理异步测量。event 最早在 origin 后下一个 tick 激活，避免零 dt。

同worker内模块不构成安全边界；Host对整图声明预算求和准入，不只检查某次碰巧激活的模块。当前共同声明上限20ms，原生/浏览器整批墙钟分别为30/40ms，均为experimental后端profile。Supervisor从Authority开始编码到完整响应接收/解码判断截止，及时结果仍须在activation+6tick门通过权限和语义检查；早到不提前、晚到不补交。模块自报update耗时仅供观测，不是可信CPU配额；本机普通进程和浏览器Worker均没有逐模块硬隔离，服务端OS配额仍待实施。

必要输入缺失/过期时跳过该模块，产生 `INPUT_UNAVAILABLE`，不调用玩家函数，也不自动填零。可选输入由玩家处理。缺测跳过不累计为执行失败。输出先整批验证：任一输出非法则该模块本次输出全部拒绝；共享 Runtime 内其他已完成模块的合法子批次可以提交。整个 worker 超时/崩溃时未返回的批次全部丢弃。

输出数值非法、错误帧或错误时间不进入 Topic。普通异常、`NotImplementedError`、依赖失败、超时分别诊断；超过连续 3 次失败或一次硬资源越界，模块/worker 进入 faulted。共享 worker 的死循环必须由 Supervisor 在外部终止，不能只靠 Python `try/except`。控制器按 03 的 cmd_vel_timeout 清空过期目标，租约撤回时立即要求零目标；位姿按 04 变旧并消失。

## 直接调用与 Topic 的混合方案

### 一次性准备任务

Navigation C5的GlobalPlanner是出发前准备任务，不是周期Module，也不加入四模块20ms声明额度。`communication.runtime.preparation`是配置单源，编译后的Manifest派生同名声明；旧Manifest新增该声明须预览显式升级。其输入为授权原始OccupancyGrid、公开起终点及安全参数，输出为map路径或None，原生/Pyodide完整往返均独立5秒。消息绑定run/deployment/task/request/operation，Schema见 [准备消息](schemas/preparation-task.schema.json)，完整合同见 [42](42_NAVIGATION_GLOBAL_PLANNING.md)。

候选Worker先完成解释器/项目测试初始化；收到计时请求后才导入、构造和调用规划器。Authority验证结果后仅交付冻结静态路径，再初始化周期图。系统setup/reset不调用规划器，规划缓存/可变对象不跨阶段授权；任意其他Python计算不产生替代路径提交入口，也没有逐模块硬CPU隔离承诺。测试与正式部署分别新建Worker，各规划一次，关闭/超时清理沿用外部Supervisor；行驶阶段仍执行41的墙钟及6tick门。

同一模块内部的矩阵运算、滤波器对象和工具函数直接调用，便于初学者和单元测试；模块之间通过声明端口连接到类型化 Topic，以便替换系统模块、录制、权限与调度。不得通过直接持有另一个模块实例绕过 Contract。

每个机器人初期一个隔离 worker，按稳定模块 ID 顺序处理同一批待激活模块；所有输入先冻结。输出在固定 `output_commit_tick` 才可见，哪怕计算很快。单写者与模块分组提高可分析性，代价是至少一个调度量子的延迟，不承诺零拷贝或 ROS 级功能。

## 渐进式编程自由

| 阶段 | 玩家编辑面 | 同一系统如何执行 |
| --- | --- | --- |
| 1 函数 | `solve(encoder, imu, dt) -> Pose2D` | 生成的 `FunctionModule` 包装器绑定同一 Contract |
| 2 类 | `Module.setup/update/reset` | 玩家接管状态与更新，端口不变 |
| 3 多模块 | 多个文件与 Contract | Manifest 连线，保留原函数/工具库 |
| 4 手动 Topic | `ctx.publisher(port)`、`ctx.subscribe(port)` | 仅声明端口，subscribe 仍读快照，publisher 仍收集批次 |
| 5 完整项目 | `RobotApp` 组装图、配置与复用包 | 只在初始化组装，经 Host 校验后冻结，与 Manifest 表达等价 |

`FunctionModule` 和 `RobotApp` 是拟提供的 SDK 适配层，不是两种不同权限模型。函数包装器在模板中显式绑定输出 frame：任务授予地图对齐时可用 map，否则用 odom，不能默认偷用 world。若 M1 需要已知起点，由任务明确公开初始位姿并经初始化配置传入；后续周期定位 fix 须另注册传感器 Schema，不能读取隐藏 spawn。高级模式也不允许自己推进仿真、取消截止、任意连服务器、访问真值或在 import 时启动无界线程。异步后台计算如未来确有需要，须新增“输入版本＋结果适用 tick＋取消”的 Contract 后再开放。

## 备选、开放问题与验收

全部用函数调用耦合太强；全部暴露原始 JSON 增加学习负担；以 Python 线程隔离模块无法可靠终止死循环。采用模块内调用、模块间 Topic、机器人级 worker。单 worker 让一个模块卡住整台机器人，后续可按风险/预算分 worker，需记录部署拓扑而不改算法端口。

开放项：event批处理的规模性能、持久检查点、动态组装和更多平台。课程数学库白名单与编辑器类型帮助已实现，见 [19](19_LEARNING_GUIDES_AND_SE3.md)、[23](23_PLAYER_CODE_AND_LIBRARIES.md)。验收包含类型/连线/依赖静态检查、缺输入、异常、重置、多文件import、超时、过期/错帧输出及适配器行为；文档AST检查不能代替SDK片段执行与Contract测试。

## M1 可用 API 与后续能力

M1 实现 `Module.setup/update/reset/teardown`、不可变值类型、`Sample`、`Inputs.latest`、`ModuleContext.simulation_tick/dt_seconds/output_commit_tick/config/publish`；输出收集到固定提交门，经 Authority 再验证。Host 从唯一 `config/game.yaml` 派生生效 Contract（period=60/10，deadline=commit_delay_ticks），避免第二份硬编码控制参数。示例端口 wheels:joint_state@1、imu:imu@1 → pose:pose2d@1；SDK 初始化仅公开起点、轮几何和模块自身配置。

M1 原始子集仅运行一个 periodic Module。M5 已补同步周期/event 多模块、依赖初始化、分组校验及自动模板，当前接口见 [26](26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)。FunctionModule/RobotApp、动态手动 Topic、ctx.rng/log/state 与检查点仍未实现。标准库/宿主文件/网络在普通 CPython 进程中没有被安全隔离；只能运行本人可信代码，不能把“ctx 未暴露引擎”说成“已经沙箱化”。[实际测试](../tests/test_m1.py) 会执行本文 SDK Python 片段并检查发布类型，同时独立验证真实外部 worker。

## M1b 增量 API

已增加不可变 `TurretVelocity`、`FireCommand`、`FireResult`、`WeaponState` 与 `ctx.fire(port="fire", request_id=None)`。ctx.publish 收集炮台速度 Topic；ctx.fire 收集离散命令并返回 ID，结果从后续武器状态读取，不阻塞算法。只有启动配置授予 robot 控制源时，对应输出端口才出现在 Contract；声明端口不等于自动获得权限。新示例单独位于 [weapon_demo.py](../examples/robot/weapon_demo.py)，保留原定位源码；接口、时序、反馈字段与可执行片段见 [14](14_WEAPONS_DESIGN.md)。炮台/武器输入为可选授权观测；M1b当时仍复用单periodic Module；当前模块图已在M5实现，此处仅记录武器API来源。

## M2 运行适配

`runtime/module_runner.py` 是原生 CPython 与浏览器 Pyodide 共用的生命周期和类型化输入/输出实现；仅运输与外部截止管理不同。浏览器多文件部署复制到独立 MEMFS，不挂载宿主目录、不加载 Authority 包。API 形状和固定提交门不变；完整安全限制见 [16](16_BROWSER_RUNTIME.md)。

## M4 函数与状态类

新增不可变 `RadarDetection(observation_id, range_m, bearing_rad)`、`RadarData(detections)` 和 `TargetEstimate(x_m, y_m, covariance=None)`。雷达检测对象集合为 tuple；协方差使用只读 float64 ndarray（Pose 为 3×3、Target 为 2×2），SDK 在 JSON 边界转换为原来的扁平序列；`ctx.publish("target", value, frame_id="map", simulation_tick=...)` 仍通过原批次收集与提交门。自身系统位姿经授权后解码为 `Sample[Pose2D]`。

C1 只需实现坐标转换函数，C2 实现保存状态的 `Tracker.update(measurements, dt)`；生成的 `CampaignRobot` Module 负责适配 Sample/端口，同一 Contract 与 Manifest 跨三关不变。模板和错误语义见 [18](18_CAMPAIGN_DESIGN.md)；这是前三关的兼容包装；C3 起经预览升级为坐标变换→跟踪→瞄准三模块图，算法文件保留，接口见 26。

## 关卡学习接口与 NumPy

所有关卡提供输入输出约定、字段单位、合成示例和带类型的脚手架。C1 返回 `NDArray[np.float64]` 的 4×4 SE(3) 矩阵；`tankbot.transforms` 校验矩阵并提供齐次雷达点，真实 wrapper 使用 `T @ p` 后发布既有 TargetEstimate。C2 只接收地图测量并保留状态。NumPy 是预装 Runtime 能力，不需要玩家写依赖/网络/JSON；详细工具、类参考与迁移见 [19](19_LEARNING_GUIDES_AND_SE3.md)。

课程依赖现按 [23](23_PLAYER_CODE_AND_LIBRARIES.md) 白名单检查：外部包仅 NumPy，另有指定基础标准库和项目模块。SDK 数值矩阵优先 ndarray；self.estimate 等状态不自动持久化。print/traceback 反馈和项目行号定位见 [24](24_RUNTIME_LOGS.md)。

C3/C4 的 PolarTracker 输入与 C2 一致使用类型化观测元组：`measurements: tuple[PolarTargetEstimate, ...]`，读取 `.range_m`、`.bearing_rad`；空帧为 `()`。同类对象作为返回值时表示玩家估计，作为输入时仅保存原始带噪观测。`own_pose`、内部状态和协方差仍使用 NumPy；C5 装甲矩阵接口不变。具体签名与旧接口迁移见 [28](28_WEAPONS_PROGRESSIVE_ESTIMATION.md)。

## 可选内部诊断

不改变算法签名或强制某种滤波器。模块update期间可以调用tankbot.diagnostic(name,value)，或ModuleContext.diagnostic；名称、元素数量和本批事件上限须由关卡显式授权，有限NumPy数组按行展开。越权/超量/非有限值报错，Authority复核；观测不进入执行器，也不影响固定提交/预算。首版仅在C2实验开放，详见 [38](38_ENGINEERING_AND_ALGORITHM_LAB.md)。

## Navigation连续追踪合同

`PathFollower.update(estimated_pose: NDArray[np.float64], path_xy: NDArray[np.float64], dt: float) -> Twist`用于Navigation C4。estimated_pose是只读map系(3,) `[x,y,yaw]`，path_xy是只读map系(N,2)米制坐标；使用SDK `readonly_path(points)`构造后，不能重新打开写权限。缺少、过期或错误帧的玩家位姿时，受管适配器输出零参考。

PathTrackingModule只订阅玩家EKF候选，公开路径一次经受权启动配置提供，不每批复制或引入新中间件。四模块仍按既有冻结输入和6tick提交，Twist先进入原轮控制器，Authority独立拒绝负vx及非平面输入。旧WaypointController/Goal和其他课程接口保留；合同样例见 [path-follower-contract.json](examples/path-follower-contract.json)，完整教材见 [40](40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)。

## 局部导航组合合同

C6同一周期导航模块先调用PathFollower，再调用LocalController，仅发布一份最终Twist参考；另有显式内部指令诊断。pose/scan/wheels均为可缺失端口，适配器必须运行零参考保护，不能因缺失输入跳过后保留旧指令。采样年龄与命令链延迟分别计算；不使用真值补齐。具体接口与生命周期见 [43](43_NAVIGATION_LOCAL_AVOIDANCE.md)。C6声明分配为轮控制4、里程计2、EKF4、组合导航10ms，总额仍20ms；这是准入分配，非独立CPU硬配额。旧关合同保持原值。
