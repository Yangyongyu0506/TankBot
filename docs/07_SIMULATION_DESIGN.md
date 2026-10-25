# 07 仿真、时间语义与 Replay

## 目的、范围与约束

定义二维权威仿真、传感器、多频率模块与异步执行的统一时间模型。ADR-0010 接受固定步长和边界提交，ADR-0011 接受分层确定性保证。M1 频率、伺服、接触与轮组参数已经用户确认并完成本机探针，见 [13](13_PHYSICS_MODEL_DECISIONS.md)；Radar 与完整跨平台部署仍未实现；M1b 武器增量见 14，不能由本机测量外推性能。

## 物理模型与核心接口

目标 `World` 设计保存静态墙体/碰撞几何、坦克刚体状态，并在后续增加炮塔朝向、弹丸、生命与规则状态；M1 原范围为静态地图/车体；M1b 已增加双刚体炮台、弹丸和命中记录，生命/完整规则仍未实现。公共控制目标采用车体 Twist（vx/vy/wz），M1 Chassis Controller 同时实现差速 vx/wz 与径向全向轮 vx/vy/wz，由场景选择。ControllerProfile 公开能力、各轴限值和 watchdog，叠加有上限的加速度、转动与碰撞响应；Encoder 来自相应轮子运动模型而非直接读取全局位姿。后续可增加独立轮电机、空转/轮滑与不同地面参数，但必须版本化模型和传感器，不能仅开放横向瞬移。

`GameCore.step(actuator_inputs) -> StepEvents` 只处理已验证执行器输入，固定 dt 来自不可变 SimulationProfile；不持有网络、Renderer、Python 或墙钟。Host 将获准的 Twist/离散操作转换为 `ActuatorInputBatch`，包含目标、原始生成 tick 与失效事件；Core 内 Controller 保存最新目标并按仿真时钟检查超时、执行运动映射。地图只在场景构建/明确规则事件时改变。Physics Adapter 封装 Rapier2D 或备选 Box2D，支持静态几何、接触、射线、shape cast 和必要的连续碰撞。弹丸速度高时须使用 swept test/CCD，定义同 tick 多碰撞的稳定排序和反弹上限，不能仅依靠离散位置重叠。

地图单位是米，坦克尺寸、速度、弹丸半径、反弹衰减、穿透容差作为版本化 `SimulationProfile`。同一命中只生效一次；同时命中按 `(tick, projectile_id, hit_index)` 等稳定键处理，不能以哈希遍历顺序或线程先完成者决定胜负。

## 时钟与不同频率

| 子系统 | 建议起始频率 | 说明 |
| --- | --- | --- |
| Physics | 60 Hz | `dt = 1/60 s`，整数 tick 为权威 |
| Encoder / IMU | 30 Hz | 每 2 tick，易对齐测试与模块 |
| Radar | 5 Hz | 每 12 tick，独立含噪/延迟模型 |
| Odometry / Control | 10 Hz | 每 6 tick，默认 deadline 为 6 tick |
| View Snapshot | 30 Hz（当前 profile） | 与 Physics/Render 独立配置，授权裁剪后发送 |
| Render | 浏览器可用刷新率，目标 60 FPS | 插值授权样本，不推进物理 |

首发频率必须能用整数 tick 表示；不支持的频率在配置时拒绝，不静默四舍五入。未来需要非整数比率再引入有理数调度器。周期相位从模块的 `origin_tick` 计算，热部署不用旧 run 起点计算首次 dt；见 05。`simulation_time_ns = floor(tick × 10⁹ / physics_hz)`，时间差计算保留 tick 的精确比率，不能累计 16,666,666 ns 产生漂移。

## 单个 tick 的确定顺序

边界 `n` 的世界状态为 `S_n`；初始化生成 `S_0` 与 tick 0 的初始测量。按以下顺序执行：

1. **提交门**：封闭本边界入口，收集 `output_commit_tick=n` 且按时完成的批次，按稳定模块/端口顺序验证与提交；迟到批次拒绝。
2. **传感器交付**：交付计划在 n 可见的测量，保留其原始采样 tick。更新合法 Topic 缓存。
3. **算法激活**：对到期模块冻结输入快照，发 RuntimeStepRequest；不在此等待。依赖于本边界已提交输出的模块现在可读到它们。
4. **View 与评估**：基于 `S_n`、选中估计与授权观测构建快照/评估；不得读取未提交的运行结果。
5. **物理推进**：Core 的底盘控制器读取本门已提交的最新目标，检查来源生成时间与配置的 watchdog，以可实现速度/制动目标作用于 `[n,n+1)`，积分到 `S_(n+1)`，生成碰撞/规则事实；采样到期传感器，加入未来交付队列。

因此激活 tick 为 6、deadline=6 的输出只在 tick 12 的提交门生效；早完成也不提前提交。估计描述 tick 6 的状态仍保留 timestamp=6，不伪装成 tick 12。Twist 同样保留生成 tick=6，生效 tick=12 是 Host 的内部调度记录，不由玩家写入速度 payload。外部键盘输入由 Host 分配下一可用门；回放记录该门以重现异步交付。所有同批次模块先冻结输入，不能读到同批次其他模块尚未提交的输出。

目标在新消息间由控制器保持；`cmd_vel_timeout` 从生成时刻计算，晚到不能延长生命期。失效后目标归零，实际减速服从动力学。失去租约、断线、reset、部署切换立即清空；接入新目标也不能恢复旧部署的缓存。该看门狗是控制器逻辑，不是执行起止时间接口，见 [03](03_PROTOCOL_SPECIFICATION.md) 和 [ADR-0014](adr/0014-ros-style-velocity-interface.md)。

同一机器人最多一个未完成 Runtime 批次；下个激活点仍未结束则跳过/记超时，不累积无界任务队列。Contract 要求 `period_ticks ≥ deadline_ticks`，event 的最小间隔也如此。初期 profile 令同机器人所有模块共享 `commit_delay_ticks=6`，Contract deadline 必须与之相同，一个请求因而只有一个 `output_commit_tick`。不同模块频率仍可不同；异质 deadline 留给后续分批/多 worker 设计，不能在现有字段里含混表达。一个 worker 可按稳定顺序执行多个到期模块；Host 记录子模块成功/失败，整 worker 卡死则丢弃整个未返回批次。数据延迟与这段计算延迟分开记录。

## RuntimeStep 接口

控制面在 `/runtime/step` 使用 service 配对，玩家代码不能任意调用。`runtime_step_request@1` 的负载示例：

```json
{
  "step_id": "step-6",
  "activation_tick": 6,
  "output_commit_tick": 12,
  "modules": [{"module_id": "odometry", "dt_ticks": 6}],
  "inputs": []
}
```

`inputs` 是至多 128 个已授权 Envelope 的快照；空数组可表示没有可用测量，必要输入模块由 Host 标记跳过，不能凭空生成零测量。响应 `runtime_step_result@1`：

```json
{
  "step_id": "step-6",
  "results": [{"module_id": "odometry", "status": "completed", "error_code": null}],
  "outputs": []
}
```

Supervisor 将结果绑定到 `(run_id, deployment_id, step_id)`，验证每个输出端口、源、所属模块与上下文。失败模块不得附带可提交输出。Module 的日志不算输出消息。返回只代表计算结束，最终仍由 Authority 提交或拒绝。

## 实时、受控测试与截止

**实时模式**按 Host 单调墙钟安排物理 tick；deadline 是对应提交门打开前收到完整结果。同 worker 的模块预算先经准入，其和受机器人批次硬限额约束；Supervisor 在 worker 外计量整个批次的墙钟与资源，到限即终止或拒绝。不能凭 SDK 自报耗时声称模块间有独立安全配额。OS 调度带来的抖动无法消除，Arena 记录实际超时与资源配置。

**受控测试模式**在提交门允许等待指定 Runtime 的有界墙钟预算，然后提交到同一固定逻辑 tick；逻辑顺序不随计算速度变化。等待超限仍失败，不因“离线”而无限运行。它用于算法对比，不作为所有硬件上都得相同超时结果的承诺。Core API 的一次 step 始终不等待玩家代码，等待由测试 Host 在外执行。

渲染丢帧时物理不改步长。单人可暂停或以慢墙钟推进；每轮最多追赶 5 个固定 tick，超过后报告 `HOST_OVERRUN` 并放慢实际播放速度，不跳过仿真 tick。竞技服务器超载应暂停/作废整场并保留证据，不选择性让某个机器人少算。浏览器后台节流时暂停本地场景；不能宣称后台保持实时竞技。

## 传感器与随机性

每个传感器定义采样周期、帧/标定、视场、遮挡、最大量程、噪声、偏置、漂移、量化、丢失概率和延迟分布。按 `(match_seed, robot_id, sensor_id)` 派生独立 RNG 流，固定算法与版本；新增一个传感器不改变其他传感器噪声序列。玩家算法 RNG 使用另一个公开派生流，不暴露可反推秘密地图/敌人的物理与传感器种子。

Radar 输出自传感器系的距离/方位测量和临时观测标签，不发布精确敌方位置/稳定世界实体 ID。Encoder、IMU 的测量差异须来自公开模型；不能一边宣称轮滑、一边把真实全局速度当无噪 Encoder。初期可简化噪声，但 profile 必须显式声明“无偏置/无丢失”等条件。

## 确定性保证的范围

| 层级 | 可承诺的条件与限制 |
| --- | --- |
| D0 逻辑确定 | 相同 tick 顺序、命令、配置、种子和稳定对象顺序 |
| D1 同构建重放 | 同一原生/WASM 构建、物理库、执行 profile 与记录接受输出；通过哈希/容差回归后承诺 |
| D2 算法重跑 | 额外固定 Python/依赖、输入交付序列、RNG、哈希种子、数值库线程配置与受控调度；算法本身不得依赖墙钟/系统熵/未控线程；仍需测试数值与预算差异 |
| D3 跨平台比较 | 用轨迹/碰撞/得分容差做验证，不承诺位级一致 |

固定 dt 不消除浮点、数学库、集合顺序、并行求解和异步截止差异。默认采用稳定 ID/排序、禁用核心中的墙钟决策和未控线程；受控 Python profile 固定 `PYTHONHASHSEED` 和数值库线程数，无法约束的算法只记录实际输出，不承诺 D2。不为了“绝对确定”立刻改固定点物理。Rapier 的增强确定性与 Box2D 的确定性均有版本/条件限制，库承诺不自动覆盖 TankBot（[Rapier](https://rapier.rs/docs/user_guides/templates/determinism)、[Box2D Simulation](https://box2d.org/documentation/md_simulation.html)）。

## Replay 设计

记录头包含 Replay 格式版本、Core 构建摘要、Schema bundle 摘要、依赖/编译目标、协议/SDK/内容/物理/ControllerProfile/执行 profile、场景摘要、部署摘要和参与者绑定。私有日志另含种子与初始真实世界；玩家公开回放不得继承它们。

每条记录保存 `run_id`、tick、`ingress_order`、类别与负载。记录实际接受的控制目标及其生成/内部提交时刻、控制器配置/看门狗失效与零目标、传感器采样与交付、玩家候选输出、拒绝原因、运行超时、能力/选源/部署切换、暂停与外部输入，以及周期状态摘要/授权视图关键帧。日志分块、校验完整性、限制容量，禁止把秘密私有回放通过普通 UI 下载。

| 用途 | 回放来源 | 不保证的内容 |
| --- | --- | --- |
| 物理/规则重放 | 初态、种子、记录的已接受命令和规则事件；不重跑 Python | 换物理版本后仍逐位相同 |
| 算法输入重放 | 原样传感器与 delivery tick，加载另一部署 | 换算法后世界仍沿原轨迹，因输入是录制的离线数据 |
| 闭环版本对比 | 同场景种子，在受控仿真分别运行版本 | 分叉后的传感器应重新模拟，不能混用原轨迹测量 |
| 视觉回放/调试 | 授权 DTO 和选中估计；按观众权限生成 | 全知关键帧能安全给活跃参赛者 |

seek 后新建 `run_id` 并清空消息/插值历史。初期从初态重新执行到目标 tick；快照恢复须验证完整物理内部状态、RNG 和队列，不能把“保存位置”当作确定性回滚。Arena 原始 Replay 只供可信审计，公开版在赛后按政策另行生成。

## 替代方案、开放问题与验收

可变 dt 实现方便但损害传感器时间与可复现性；每 tick 同步等待 Python 会阻塞所有机器人；按消息到达立即应用会让机器速度改变控制语义。采用固定步长、批次与定点提交，代价是输入到控制的明确延迟，需在教学与控制参数中体现。

开放项：物理库、子步数、高速弹丸 CCD 成本、真实预算与采样频率、Replay 压缩。验收包含时间戳公式、同 tick 稳定排序、延迟乱序、输出早到/迟到、重置旧消息、worker 无限循环、Host 超载、同构建重放，以及错误估计不影响真实碰撞。

## M1 物理配置、数值误差与录制

唯一数值来源为 [config/game.yaml](../config/game.yaml)，结构受 simulation-profile Schema 校验，跨字段约束由 Host/Core 校验；缺失参数、未知模式与非整数采样比拒绝。`solver.dt` 必须等于 `1/(physics_hz*substeps)`，不静默覆盖矛盾值。Rapier 引擎 profile 完整显式保存；只在升级审查时用 `cargo run --example solver_profile` 导出候选默认设置，不在运行时补缺。刚体不额外使用引擎阻尼/休眠，受力仅来自已确认伺服、地面阻力与接触。

每主 tick 四个显式子步，各次重算车体系伺服和阻力再旋转到世界系；每子步运行 Rapier 接触求解（8 solver / 4 PGS / 1 stabilization）。圆角矩形的外包尺寸包含圆角，碰撞形状的核心半长/半宽需减去圆角半径；质量和惯量用独立 MassProperties，不由碰撞外形隐式推导。接触恢复系数零，有限容差仍可能产生微小穿透；验收量测误差，不承诺数学上严格不重叠。

M1 编码器采用理想轮速反算与积分，IMU 对质心世界速度变化作旋转后窗口平均，含碰撞冲量；公式见 13。差速横滑是不可由左右轮编码器恢复的误差来源，不能回读真实位姿消除漂移。

Authority 的有界私有记录保留 tick、执行器实际提交、真实位姿/速度；测试将实际提交的目标重新注入全新同构建 Core，逐 tick 比较。环形记录达到配置上限后丢弃旧历史，当前没有完整持久化/seek/checkpoint 产品接口；不要把短程验证说成完整 Replay 系统。报告同时区分实时不等待和受控测试提交门的有界等待。M1 原阶段没有武器；M1b 已按下节加载炮台、弹道与冲量，并扩展执行器录制。

## M1b 子步增量

每个主 tick 先执行当前门的幂等发射请求（先采样炮口速度再施加后坐），每个物理子步重算底盘/炮台伺服后推进 Rapier。弹丸按子步首尾车体轨迹作连续查询，稳定顺序处理最早事件，受击冲量集中到子步末，再计入 IMU 真实速度差。传感器在 S_n 的 30 Hz 边界采样；Runtime 在 10 Hz 激活、延迟 6 tick 提交。weapon_state 在采样间保持上一样本，不能把轮询频率当作新物理事件。私有 Replay 新增完整 actuators（底盘、炮台、单发和撤销），仅重放底盘不足以复现 M1b。近似、寿命/冷却边界及验证见 [14](14_WEAPONS_DESIGN.md)。

## 显示时间层

当前 `web/rendering.js` 不推进世界；SceneTimeline 按授权快照时间与选中位姿/关节实际采样时间插值，独立 RAF 驱动绘制，相机只跟随显示 x/y。时延、丢帧/跳变/失源与模型配置见 [15](15_RENDERING_DESIGN.md)。提高视图频率不改变传感器或 Python 算法频率；重复旧估计不能制造新估计样本。

## M2 浏览器时间适配

浏览器运行同一 Authority.advance()，固定提交不因 MessagePort 到达提前。Core Worker timer 与 rAF 独立；每个边界让出事件循环但不等待 Python。外部 iframe watchdog 终止超预算玩家 Worker，缺/晚响应在原门丢弃；tab 后台降频或设备过载影响墙钟进度，不能改 simulation_time_ns 公式或伪造补偿 tick。平台差异与测量见 [16](16_BROWSER_RUNTIME.md)。

## M5 当前增量

M5 多模块使用同一冻结/提交门，支持 event 去重与实际调用 dt；模块链跨批次保留测量 tick。C3/C4 新增受限角加速度力矩输入，C4 首次表面接触装甲判定不改变子步动量模型，详见 [26](26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)。
