# 34 Navigation 控制调试与差速里程计

## 目的、范围与确认

在已有 Navigation C0 上补控制曲线，新增 `navigation.c1`（[YAML](../levels/navigation.C1.yaml)），复用玩家已有轮控制器，只增加从轮速推算位姿的任务。本轮不改变已确认的电机、接触或 C0 验收。C1 接口、权限、时序和阈值均由用户确认，决策见 [ADR-0047](adr/0047-navigation-odometry-and-control-feedback.md)。实际检查见 [验收报告](reports/NAVIGATION_ODOMETRY_VALIDATION.md)。

## 数据流与职责

```mermaid
flowchart LR
    Q[YAML 固定 Twist 序列] --> C[复用 WheelController]
    E[理想轮编码器] --> C
    C --> U[限幅 / 看门狗 / 轮电机]
    U --> P[权威物理]
    P --> E
    E --> O[玩家 Odometry.update]
    O --> K[/robot/estimates/odometry/pose]
    K --> S[Pose Selector / View Policy]
    S --> V[估计车体 / 轨迹 / 相机]
    K --> R[私有同采样时刻评分]
    P --> R
    R --> M[显式授权的累计 RMSE]
    Q --> D[控制曲线]
    E --> D
    C --> D
```

Core 仍只接受合法轮电压；估计绝不改变真实位置。控制曲线只消费系统参考指令、已授权编码器和限幅/看门狗后的执行器输入，不能从真实速度生成“传感器反馈”。

## C0/C1 控制调试面板

HUD 的“曲线”标签显示四组有单位的曲线：目标/编码器前进速度、目标/编码器转向角速度、左右轮速、左右轮电压。横轴为从首次正式控制生效开始的仿真秒；虚线表示 YAML 指令段切换，鼠标可查看采样值。“放大曲线”弹出四图面板，可用 × 或 Esc 关闭，运行中打开仍持续计时；桌面端四图同屏。结束后曲线保留，重试/切关创建新 run 并清空。编辑、测试不会填入正式曲线。

`permissions.visualization.allowed_control_signals` 是独立上限；`visualization.control_feedback` 配置标题、说明、采样周期、容量、精度和图例。当前两关每 6 tick 记录一次，最多 300 项。`ControlFeedback` 在 Authority 中维护有界记录，`campaign_status().attempt.control_feedback.points` 返回授权信号；UI 使用可选的 control_after_tick/run_id 游标轮询增量记录，累计历史仍留在两端的有界缓冲；不以轮询频率代替采样频率。旧调用不带游标时仍返回完整快照，跨 run 的游标自动退回完整快照，complete 字段区分完整/增量。这样避免每次轮询重复序列化整段曲线，机器人执行预算与固定提交时间保持不变。

每项包含 `simulation_tick`、`elapsed_ticks`、`cycle_index`、`segment_index`、`label` 和 `values`。信号注册表固定 SI 语义及单位；未知信号、单位冲突、未授权编码器、越权信号、重复图表 ID 和超限容量在加载时拒绝。授权不扩大 Python 的 Topic 权限。数据来自已解析配置与消息，不需要新增协议 Topic、依赖或物理模型。

电压是当前边界生效、经逐轮截断后的输入，零电压包括看门狗超时和撤权情况；它不是实测电流或电机端电压传感器。速度曲线由轮速 FK 得到，不声称能观测侧向滑动。

## 玩家接口与生成文件

`control/wheel_controller.py` 保留；本关只高亮新增的 `localization/odometry.py`。框架构造 `Odometry(model, initial_pose)`，其中 `model: DifferentialDriveParameters` 复用 C0 标定；`initial_pose: NDArray[np.float64]` 是一次公开的地图系 `[x_m,y_m,yaw_rad]`，只读 `(3,)`。玩家持有自己的可写 `self.pose` 副本。

```python
def update(
    self,
    wheel_rates_radps: NDArray[np.float64],
    dt: float,
) -> NDArray[np.float64]:
    """只读左右轮速 (2,)，rad/s；返回地图系 [x_m,y_m,yaw_rad] (3,)。"""
    raise NotImplementedError
```

输入输出均要求 float64 NumPy 数组。玩家自行选择 Euler、中点等积分；框架不代做 FK、坐标旋转或积分。教学说明给出 `v=r(ωL+ωR)/2`、`w=r(ωR−ωL)/B` 和地图系状态方程，提供单位、轮序、类型、返回形状与常见错误。

系统文件 `localization/odometry_module.py` 负责按轮名取值、重复采样去重、时间差、返回验证、yaw 归一化和发布。只保存上次采样 tick，不积累无界历史。发布使用既有 `pose2d@1`，候选 Topic 为 `/robot/estimates/odometry/pose`，frame 为 `map`、child 为 `base_link`。Selector 独占标准 `/robot/localization/pose`。

## 时序、估计与评分

物理 60 Hz/4 子步、理想轮观测 30 Hz；轮控制与里程计均为 10 Hz，固定 6 tick 提交。两个Module Contract各声明10ms，合计20ms用于图准入；不是每模块强制截止或整批墙钟。后端墙钟及冻结/兼容合同以 [41](41_RUNTIME_EXECUTION_PROFILES.md) 为准，输入冻结和6tick门保持。

`dt` 使用本次与上次实际处理的编码器样本 tick 差，不是显示帧间隔或输出提交时差。每次调用取最新轮速，因此低于传感器频率的数值积分仍有近似误差；不伪装成处理了全部 30 Hz 测量。输出时间戳标记所估计的采样 tick，而非提交时刻。

`evaluation.source: player_pose` 明确选择自身估计评分，默认仍为原 `target_estimate`。Authority 使用有界 `_self_pose_history`，只对当前选中的玩家候选按同 tick 真值评分；未开始、早于尝试起点、重复/倒序、无匹配真值、未对齐的 odom 坐标或其他来源不计数。历史不进入 SDK、公共视图或管理响应。6 tick 延迟不作为位置误差，评分也不外推估计。

沿用 C0 24 秒、四次直行/原地左转；最后段结束立即结算并冻结。成功必须同时满足 YAML 中五项条件：终点距离≤0.30 m、真实路程≥7.2 m、累计位置 RMSE≤0.15 m、累计最短弧朝向 RMSE≤0.10 rad、有效估计≥100 次。没有有效估计时误差在公共响应为 null，规则内部视为未达标，不能以零误差通关。运行故障优先失败，其后判断成功、`estimation_failed`、超时；主动结束/重试保留。

`evaluation.live_feedback` 兼容旧单对象，也可声明多个指标；两项 RMSE 必须分别在 `allowed_metrics` 中授权。它们只是聚合教学反馈，不公开实时真值位置/方向。终局只统计结束前已提交的样本，不等待或补算未提交批次；显示位姿可晚于当前物理状态，这是明确的提交延迟。

## 信息边界与项目升级

C1 禁用 System Pose Provider，允许地图和玩家位姿；没有合法候选则不显示全局车体/跟随真实位置。估计错误照常显示，过期沿用已有淡出/隐藏规则。开发者真值使用独立通道和显式图层。Runtime 不获得 `/robot/localization/pose` 输入；里程计模块只连编码器，控制器仍连参考 Twist 与编码器。

C1 在 C0 后解锁，稳定 ID 不随文件名变化。两关共用 `workspace_scope: navigation`，Weapons 工程保持独立。解锁只补缺失文件；已有控制器和里程计不覆盖，历史 revision 可恢复。C0/C1 的连线、位姿来源和预算不同，系统脚手架更新走既有预览/显式应用流程；来源不符合当前权限时提示升级，不让旧系统位姿越权显示。新增里程计错误使用已有 Python traceback 日志。

## 取舍、限制与验收

返回 NumPy 位姿向量减轻 SDK 组织负担，代价是框架必须严格检查形状与单位说明；直接返回 Pose2D 是可选替代，本关采用已确认的数组接口。累计 RMSE 避免仅检查闭环终点而漏掉全程错误；不增加未经确认的唯一路径、积分方法或逐帧精度门槛。

本轮不增加编码器噪声、IMU 融合、轮胎打滑、定位地图、路径跟踪或后续课程。验收包括参考解成功、静止/偏移估计失败、采样时刻对齐、重复/未知样本、错误数组 traceback、权限隔离、有界曲线、C0→C1→C0 源码保留，以及原生和浏览器的真实编辑/测试/部署。
