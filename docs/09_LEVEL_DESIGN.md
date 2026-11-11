# 09 关卡、教学接管与游戏模式

## 目的、范围与要求

把渐进失去信息转化为渐进建立能力，而非指定算法题库。关卡复用Core、SDK、Runtime、Protocol与View Policy，不按关卡复制引擎。Weapons见 [18](18_CAMPAIGN_DESIGN.md)、[28](28_WEAPONS_PROGRESSIVE_ESTIMATION.md)；Navigation C0–C6已实现轮控制、里程计、GPS/EKF、航点闭环、连续路径追踪、已知地图规划与局部静态避障，接口分别见 [33](33_NAVIGATION_MOTION_CONTROL.md)、[34](34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md)、[35](35_NAVIGATION_GPS_LOCALIZATION.md)、[37](37_NAVIGATION_WAYPOINT_CONTROL.md)、[40](40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)、[42](42_NAVIGATION_GLOBAL_PLANNING.md)、[43](43_NAVIGATION_LOCAL_AVOIDANCE.md)。

现有十三关使用独立levels/*.yaml，统一发现、校验、加载和解释，不按ID选择行为；源格式见 [27](27_LEVEL_PLUGIN_ARCHITECTURE.md)。公共c0后分为Weapons和Navigation两条独立主线，各自内部保留真实代码依赖，见 [36](36_BRANCHING_PROGRESSION.md)。

关卡必须同时声明：问题、撤回的系统能力、新授权输入、前置技能、可保留代码、反馈与可达成的验收标准。撤回能力前先给替代输入/模板和安全试验场。每次引入尽量只改变一个主要认知负担。

## 当前章节与后续教学顺序

| 章节 / 关卡 | 游戏问题与信息变化 | 新能力与复用 | 验收方向 |
| --- | --- | --- | --- |
| Hello Robot / C0 | 全知驾驶与武器练习 | 系统自身位姿、地图、人工底盘/炮台/单发 | 移动、转向、命中 |
| Weapons / C1 | 隐藏敌方位置，理想 Radar；锁定驾驶 | NumPy SE(3) 矩阵坐标变换 | 发布估计并人工瞄准命中 |
| Weapons / C2 | 中心观测加入较大噪声和丢失 | 复用 C1，状态类跟踪 | 存活击杀巡逻敌车 |
| Weapons / C3 | 直接接收车体系原始距离/方位 | 非线性观测滤波，输出仍为 r/theta | 人工瞄准，存活击杀 |
| Weapons / C4 | 沿用 C3 中心 Radar/差速敌车，撤回人工武器 | 复用极坐标滤波，中心预测与角加速度闭环 | 自主整车击杀 |
| Weapons / C5 | 改用匿名装甲观测，敌车全向小陀螺 | 匿名装甲关联、等价相位估计、多文件预测与炮台闭环 | 自主装甲击杀 |
| Navigation / C0 | 根据Twist与实测轮速执行轮电压控制 | 独立工程、FK/IK与电机反馈，不复用Weapons代码 | 固定序列末终点距离与实际路程 |
| Navigation / C1 | 系统不再持续提供自身位姿 | 复用轮控制器，积分轮式里程计 | 同采样时刻位置/朝向RMSE及运动条件 |
| Navigation / C2 | 编码器漂移、低频带噪GPS | 复用控制器/里程计，实现EKF并比较轨迹/协方差 | 固定EKF评分、实际路程与全程估计误差 |
| Navigation / C3 | 从固定指令转为公开航点任务 | 复用轮控制器/里程计/EKF，新增位置反馈产生Twist参考 | 按序到点、终点停稳、限时完成；RMSE作反馈 |
| Navigation / C4 | 仓储障碍场地的完整公开路径，连续追踪不逐点停车 | 复用轮控/里程计/EKF，新增PathFollower；路径由可信裁判生成 | 顺序检查点、真实折线距离RMSE、最大偏离、无接触及终点连续停稳 |
| Navigation / C5 | 完整已知原始网格和公开目标，撤回裁判路径 | 玩家膨胀、搜索、后处理；复用四模块闭环 | 5秒合法规划，120秒内无碰撞到点停稳；不设C4误差/检查点门槛 |
| Navigation / C6 | 先验地图漏标一个静态方障碍，新增带噪距离扫描 | 复用五项算法，同模块LocalController自主减速、绕行和接回路线 | 120秒内无碰撞到原终点并停稳，合理绕行不增加误差或检查点门槛 |
| 后续章节（待设计） | 未知环境、动态避障、决策、完整自治 | Localization / Mapping / Planning | 无人工执行器闭环；不强制指定算法 |

Weapons C1–C5不允许人工/程序驾驶，零目标主动制动并保留受力；C1–C3保留人工武器，C4/C5授权程序炮台角加速度和单发。Navigation只保留底盘，使用独立navigation工程，Weapons和公共入门沿用campaign工程；两条主线共享同一个版本1进度文件，按稳定ID分别记录完成项。公共c0后可交替学习，Navigation C0不要求Weapons C5。全部硬前置由metadata.prerequisites声明；展示顺序和学习建议不产生权限。跨scope切换原子重建Authority/Workspace并清除会话测试/部署，保存的源码、revision、ledger与历史保留。地图覆盖只作练习，不奖正式进度。旧“C3自身定位/C4建图”方案已撤回。

C0与Weapons使用共享空旷场地，Navigation C0–C3亦为空旷场地，C4–C6引用同一仓储地图资产，C6另有独立生成的私有物理障碍。C4裁判搜索、平滑与安全复验已实现；C5由玩家对原始占用网格实施安全膨胀与全局规划；C6以扫描处理漏标静态障碍，见43；IMU融合和SLAM课程仍为Planned，见 [39](39_NAVIGATION_COURSE_PROPOSALS.md)。

## 当前LevelDefinition与能力接管

正式源是 [level.schema.json](schemas/level.schema.json) 约束的独立YAML，具体字段和现有组件见 [27](27_LEVEL_PLUGIN_ARCHITECTURE.md) 与 [关卡编写指南](../levels/README.md)。加载器把声明编译为Core场景、Runtime grants、Selector资格、View Policy与规则；这些不是UI布尔开关。系统模块与玩家模块通过已声明端口接管功能，不修改Core算法分支。

### 历史：早期Locomotion内容草案（不作为配置输入）

```json
{
  "level_id": "future-locomotion-intro",
  "content_version": "1",
  "scenario_id": "known-maze-01",
  "simulation_profile": "training-60hz-v1",
  "execution_profile": "controlled-v1",
  "view_policy_id": "campaign-l3-v1",
  "capabilities": ["sensor.encoder.read", "sensor.imu.read",
    "estimate.pose.publish", "control.manual.drive"],
  "pose_source": {"mode": "player", "module_id": "odometry", "fallback": "none"},
  "initial_pose": {"mode": "provided_fix", "frame_id": "map"},
  "unlock_templates": [{"template_id": "odometry-intro", "version": "1.0.0"}],
  "evaluation_profile": "pose-and-route-v1"
}
```

上例保留早期Locomotion概念，不是当前YAML格式或可运行的Navigation关卡。当前navigation.c1–c6的一次初始位姿、持续传感器与玩家定位来源均由各YAML显式声明，不把隐藏spawn塞入Manifest；不开放任意脚本式LevelDefinition。

系统模块与玩家模块使用相同语义端口，例如规划器读取 `/robot/localization/pose`，只需改变来源连接就能接管定位。系统控制器可以在前期承担路径执行，高级阶段把其租约交给玩家。每次切换均在 tick 边界提交并记录，禁止直接修改 Game Core 的算法分支。

从全知关进入未知地图关时采用新场景/纪元，不能把已泄露地图重新命名为“秘密”。撤权也清除 UI 缓存和可见图层；已被用户保存的信息无法撤回，应在内容设计中承认。

## 局部可玩性与反馈

当前无合法定位时隐藏全局车体，仍可看获授权的局部测量/状态面板，结束或重试后编辑；C6新增局部scan及同tick EKF投影；通用危险提示、预测射线和独立暂停UI尚未实现。Navigation禁止人工驾驶；自由试验场的车体系键盘控制不依赖全局位姿。未来局部几何显示须先定义观测和权限，不能用真值相机生成全知局部地图。

错误估计不会被修正成真值。当前已有测量时间/过期、日志、候选估计、协方差和获授权的聚合误差反馈；这些不提供通用接触方向传感器。实时指标逐关受allowed_metrics/live_feedback约束；Navigation C4–C6仅在终局显示真实追踪误差，运行中授权距终点标量和定位RMSE。详细真值/开发者图层不能回灌活跃算法，见 [04](04_STATE_AND_VIEW_MODEL.md)。

## Campaign、Algorithm Lab 与 Arena 的复用

Campaign已提供提示、模板和解锁；Lab当前仅有Weapons C2授权输入录制与双版本滤波回放试点，见 [38](38_ENGINEERING_AND_ALGORITHM_LAB.md)。通用参数扫描、多模块/控制器闭环对照与完整Lab尚未交付。Arena计划使用服务器Authority、强化沙箱与固定赛制，仍未实现；不得由共享Core/SDK推断这些模式已可用。

Lab 的“录制输入对比”不证明控制算法的闭环表现，闭环对比须重新运行各自世界。模板测试可给理想数据帮助理解，但正式关卡使用声明噪声和时延。服务器反复评分是潜在信息 oracle，需限制返回细节和请求频率；Arena 不提供活跃比赛逐 tick 真值误差。

## 替代方案、取舍与未决项

强制特定算法容易评分却抑制探索；使用轨迹误差、完成率、鲁棒性和预算评价，允许多种解法。过早多模块增加框架负担；先生成函数包装，C3 再解释完整 Contract。自动全知纠错体验平滑却抹去定位误差；用局部提示替代。

当前十三关的参数、阈值和输入已在对应YAML确认；本轮不重新选择。未决项是长期教学效果、更多平台与未来课程的模型/传感器/验收方案。新方案须确认后实施，并使用不同参考算法检验可达性，不能把某一实现当唯一答案。

## 验收条件

- C0–C2 可在不理解网络/JSON 的情况下完成，C3 起能复用前序 Python 文件。
- 每次撤权都先有可用替代输入、模板、局部反馈与测试夹具。
- 用至少两种合理方法完成噪声跟踪/定位关，不强制算法名称。
- LevelDefinition 无需改 Core 即可切换系统/玩家 Provider；未授权频道从 Router 到 UI 均不可达。
- 全知评估、局部观测和估计显示有明确标签，关卡不会通过效果/相机恢复真值。

## 所有关卡的说明准入

从本轮用户要求起，新关卡必须提供 [19](19_LEARNING_GUIDES_AND_SE3.md) 所定义的完整学习说明：算法文件、带类型签名、字段/单位、返回语义、调用与状态、合成自测及操作步骤。初学者只填算法，框架/导入/文件结构预先准备。当前 C1 已改为返回 NumPy SE(3) 元素，并由真实矩阵乘法消费；不能继续用未解释的自定义返回值替代矩阵学习目标。
