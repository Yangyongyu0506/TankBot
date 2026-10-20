# 05 Robot Module Contract 与 Python SDK

## 目的、范围与约束

`tankbot` SDK 隐藏 JSON、网络、进程和权限细节，公开稳定的类型、模块生命周期和端口。初学者函数与高级模块采用同一份 Contract 及同一 Host 验证路径。ADR-0008 接受 Contract 和混合交互原则；以下 API 为未实现的设计接口，不能直接 `pip install` 使用。

## 类型与 Contract

SDK 核心类型是不可变值：`Pose2D`、`ImuData`、`EncoderData`、`RadarData`、`Sample[T]`、`Inputs`、`ModuleContext`、`Module`。编码映射以 03 和 Schema 为准：`Pose2D(x_m, y_m, yaw_rad, covariance, child_frame_id="base_link")`；`EncoderData(left_distance_m, right_distance_m)` 为自本 run 重置以来的累计轮距；`ImuData(angular_velocity_z_radps, linear_acceleration_x_mps2, linear_acceleration_y_mps2)`；`Sample` 包含 `data`、`simulation_tick`、`frame_id`、`sequence_number`。SDK 解码时保留时间与帧，不只传数值。

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

Contract 的 `budget_ms` 是请求的墙钟预算；Host 可以下调或拒绝。公开的生效预算写入部署报告。`dependencies` 只规定 setup 顺序，必须为无环图；Topic 控制反馈环是合法的，但跨模块边至少延迟到下一次输入快照，不能在同一回调中递归调用。

## Module API 与生命周期

```python
from tankbot import Module, ModuleContext, Inputs, Pose2D

class Odometry(Module):
    def setup(self, ctx: ModuleContext) -> None:
        self.previous_encoder = None

    def update(self, inputs: Inputs, ctx: ModuleContext) -> None:
        encoder = inputs.latest("encoder")  # Sample[EncoderData]，必要输入保证存在
        imu = inputs.latest("imu")          # Sample[ImuData] | None
        # TODO: 用测量、ctx.dt_seconds 和自己的状态计算 estimate: Pose2D。
        # 完成算法后：ctx.publish("pose", estimate, frame_id="map",
        #                         simulation_tick=encoder.simulation_tick)
        raise NotImplementedError

    def reset(self, ctx: ModuleContext, reason: str) -> None:
        self.previous_encoder = None

    def teardown(self, ctx: ModuleContext) -> None:
        pass
```

这里是模板示例，不实现里程计。`ModuleContext` 公开 `simulation_tick`、`dt_seconds`、`output_commit_tick`、不可变 `config`、按模块派生的 `rng`、有配额的 `log` 和 `state` 检查点接口。它没有 World、物理对象、宿主文件系统、真实地图 seed 或未授权变换。

`ctx.publish(port, value, frame_id, simulation_tick=None)` 在本激活批次收集输出，默认 tick 为激活 tick；候选频道与 publisher 由已验证连接绑定。返回不代表已提交。输入是快照，模块不能修改 Router 缓存。`Inputs.latest(port)` 在允许的历史内选 `(sample_tick, sequence)` 最大的合法样本；过期可选输入返回 `None`。

生命周期为 `created → initializing → ready → running → stopped`；异常可进入 `faulted`。部署时先按依赖调用 `setup`，成功后才能激活。新 run 在 tick 0 调用 `reset` 清空时间相关状态、输入历史和 RNG。调度起点 `origin_tick` 是部署生效 tick，run 重置时归零；第一个周期回调在 `origin_tick + period_ticks`，因此正常 `dt_seconds > 0`。`teardown` 有界且尽力执行，强杀时不保证运行。

模块对象字段只活在当前 Runtime。可选 `ctx.state.get/set` 保存带 `state_version` 的有大小限制 JSON 检查点，写入隔离数据区并由 Host 校验；不得 pickle 任意对象。默认部署不继承旧内存或检查点，跨代码版本恢复需显式迁移并测试。

## 调度与错误语义

| 模式 | 首发语义 | 约束 |
| --- | --- | --- |
| 同步 periodic | tick 为周期整数倍时激活，单回调不重入 | 默认模式；取该 tick 的冻结输入快照 |
| 同步 event | 指定输入有新样本时，下个可用 tick 激活 | Contract 为 `mode="event"`、`trigger_inputs`、`min_interval_ticks`；同 tick 合并事件 |
| 异步 callback | 后续研究 | v1 不接受 `async def update`，避免墙钟 await 改变仿真含义 |

周期与 event 使用同一 `deadline_ticks`、`budget_ms` 和下一边界提交机制；event 的最小间隔至少等于 deadline，periodic 的 period 也必须不小于 deadline。初期同机器人共用执行 profile 的 `commit_delay_ticks`（建议 6），各模块的 `deadline_ticks` 必须等于它，才能用一个批次生效 tick；不支持的配置在准入时拒绝。

`dt_seconds` 是距上次**实际调用的激活时刻**的 tick 差/physics_hz，首次从 `origin_tick` 算起；缺输入/忙碌跳过没有调用，因此下次 dt 累积。回调异常或输出被拒绝不会回滚任意 Python 对象字段，下次 dt 仍从该次调用算，玩家需修复/显式重置状态。`ctx.dt_seconds` 不是传感器采样时间差，算法应使用 Sample 的 tick 处理异步测量。event 最早在 origin 后下一个 tick 激活，避免零 dt。

同 worker 内模块不构成安全边界，Host 对同批模块预算做准入，生效预算之和不得超过机器人批次硬上限。模块预算用于配置与诊断，外部 Supervisor 强制的是整个批次的墙钟/OS 资源限额，不信任 Python 自报的每模块耗时。初始机器人批次上限建议 20 ms；单模块例子可独占，多模块须分配或通过经过基准验证的新 profile 调整。

必要输入缺失/过期时跳过该模块，产生 `INPUT_UNAVAILABLE`，不调用玩家函数，也不自动填零。可选输入由玩家处理。缺测跳过不累计为执行失败。输出先整批验证：任一输出非法则该模块本次输出全部拒绝；共享 Runtime 内其他已完成模块的合法子批次可以提交。整个 worker 超时/崩溃时未返回的批次全部丢弃。

输出数值非法、错误帧或错误时间不进入 Topic。普通异常、`NotImplementedError`、依赖失败、超时分别诊断；超过连续 3 次失败或一次硬资源越界，模块/worker 进入 faulted。共享 worker 的死循环必须由 Supervisor 在外部终止，不能只靠 Python `try/except`。控制输出按 03 到期中性制动；位姿按 04 变旧并消失。

## 直接调用与 Topic 的混合方案

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

开放项：event 批处理对吞吐的影响、数学库可用集、检查点上限、IDE 类型提示生成。验收包含类型/连线/依赖静态检查、缺输入、异常、重置、多文件 import、超时、过期/错帧输出，以及函数包装与等价类输出一致。SDK 示例必须在 SDK 实现后通过 import、Contract 与文档片段测试。
