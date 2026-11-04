# ADR-0048 Navigation GPS 融合定位

- Status: Accepted
- Date: 2026-11-03

## Context

Navigation C0/C1 已完成轮驱动和理想轮式里程计。用户要求 C2 引入我方 GPS，帮助玩家理解 EKF 定位，并已逐项确认轮速误差、GPS 模型、函数、时序、评分及可视化。现有 GPS 类型属于敌车截获观测，不能重定义为我方定位。

## Decision

采用 PositionFix2D / position_fix2d@1，地图系二维位置和必填2×2协方差。GPS 质心安装、2 Hz、各轴独立σ=0.20 m，无 yaw/偏置/丢失/延迟/遮挡。编码器30 Hz，每轮白噪声σ=0.20 rad/s、每次尝试独立固定增益误差±3%，轮角同步带误差；控制器、纯里程计和 EKF 共用一次采样，不给理想旁路。两个传感器使用独立命名随机流。

新增 EkfLocalization.predict/correct，维护 float64 NumPy (3,) state 与 (3,3) covariance，返回 None；适配器负责去重、时刻对齐、验证和发布。沿用60/30/10 Hz、4子步、6 tick提交，三模块预算8/4/8 ms，总20 ms。P初态由YAML声明，初始位姿只公开一次。不同 tick 的 GPS 跳过并诊断，不伪装支持乱序滤波。

24秒同一方形指令末按真实路程≥7.2 m、EKF位置RMSE≤0.15 m、朝向RMSE≤0.15 rad、有效估计≥100次通关，取消终点距离门槛。evaluation.module_id=ekf 固定评分，reference_module_id=odometry 独立对照；选显示来源不影响评分。新增可选 view_snapshot@5 投影白名单内的玩家候选，两条轨迹、GPS点、选中位姿1σ椭圆及共轴RMSE分别授权，真值仍仅独立开发者渠道可见。

不重定义 gps_fix@1，不覆盖玩家算法/历史，不按关卡ID选择行为。课程、误差和教学全部进入 navigation.C2.yaml；通用组件经现有加载/注册体系组合，详细接口见 [35](../35_NAVIGATION_GPS_LOCALIZATION.md)。

## Alternatives

轮速 + GPS 可集中训练基础 EKF；同时融合 IMU 可增加角速度信息，但需要额外的噪声、输入与时序约定。直接把 GPS 当位姿显示、让不同模块取得不同编码器样本，均会破坏本关的教学或模型一致性。

## Consequences

扩展传感器参数、SDK/Schema、教学脚手架与估计评估，不更换 Core、不引入中间件或滤波库。带误差编码器会影响控制，故不沿用终点回原点门槛；只按定位绝对阈值评分，不要求每一随机种子的每一误差都比纯里程计小。固定增益是相关误差，基础三状态EKF可用有效Q近似，允许内部增广。旧设置仅在内存补齐新增图层键，旧源码和进度不重写。

## Validation

用户确认全部设计边界，参考解、拒绝案例、252项Python回归和两种真实Firefox编辑/测试/部署均通过。有效样本239次，满足固定tick评分与终局边界；源码/历史/进度、旧关卡兼容和有界显示已检查。具体结果、部署时刻对随机序列的影响及平台限制见 [验收报告](../reports/NAVIGATION_GPS_LOCALIZATION_VALIDATION.md)。
