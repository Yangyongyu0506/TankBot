# 09 关卡、教学接管与游戏模式

## 目的、范围与要求

把渐进失去信息转化为渐进建立能力，而非指定算法的题库。关卡数据复用相同 Core、SDK、Runtime、Protocol 与 View Policy，不按关卡复制引擎代码。C0–C2 的当前实现与用户确认模型见 [18](18_CAMPAIGN_DESIGN.md)，C3–C5 的当前实现与用户确认见 [26](26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)，Locomotion 以后仍为后续设计。

现有五关已迁移到独立 `levels/*.yaml`，统一发现、校验、加载和解释，不按 ID 选择行为；实际源格式、当前组件与迁移记录见 [27](27_LEVEL_PLUGIN_ARCHITECTURE.md)。下文通用课程蓝图中的未来关卡示例不是当前可加载的 YAML 格式。

关卡必须同时声明：问题、撤回的系统能力、新授权输入、前置技能、可保留代码、反馈与可达成的验收标准。撤回能力前先给替代输入/模板和安全试验场。每次引入尽量只改变一个主要认知负担。

## 当前章节与后续教学顺序

| 章节 / 关卡 | 游戏问题与信息变化 | 新能力与复用 | 验收方向 |
| --- | --- | --- | --- |
| Hello Robot / C0 | 全知驾驶与武器练习 | 系统自身位姿、地图、人工底盘/炮台/单发 | 移动、转向、命中 |
| Weapons / C1 | 隐藏敌方位置，理想 Radar；锁定驾驶 | NumPy SE(3) 矩阵坐标变换 | 发布估计并人工瞄准命中 |
| Weapons / C2 | 中心观测加入较大噪声和丢失 | 复用 C1，状态类跟踪 | 存活击杀巡逻敌车 |
| Weapons / C3 | 直接接收车体系原始距离/方位 | 非线性观测滤波，输出仍为 r/theta | 人工瞄准，存活击杀 |
| Weapons / C4 | 新增车头 GPS，只有四侧中央装甲扣血 | 联合不同安装点与坐标系，估计 x/y/yaw | 人工装甲击杀 |
| Weapons / C5 | 撤回人工武器，敌车全向小陀螺 | 融合复用，多文件预测与炮台闭环 | 自主装甲击杀 |
| Locomotion（待设计） | 从底盘驱动、运动学、控制逐步进入自身状态估计 | 延续武器模块，逐步接管驾驶 | 具体关卡/阈值与用户共同确认 |
| 后续章节（待设计） | 未知环境、规划、决策、完整自治 | Localization / Mapping / Planning | 无人工执行器闭环；不强制指定算法 |

C1–C5 始终不允许人工/程序驾驶，保持零目标主动制动并保留受力；C1–C4 保留人工武器，C5 才授权程序炮台角加速度和单发。先解决目标感知与武器，再引入自己的运动/定位，避免同时增加两种主要负担。后续关卡编号未定，旧路线图的“C3 自身定位 / C4 建图”已经撤回，不能继续按其编号实现。

## LevelDefinition 与能力接管

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

这是未来 Locomotion 的受信内容格式草案（不是当前 C3），尚不开放玩家上传任意 LevelDefinition。引用的 profile 必须在 Host 注册且版本固定；`initial_pose` 声明交付策略，具体 fix 由授权输入提供，不把完整 spawn 数据塞入 Manifest。能力映射为 Router grants、Selector 资格、View Policy 和控制租约，不是 UI boolean。

系统模块与玩家模块使用相同语义端口，例如规划器读取 `/robot/localization/pose`，只需改变来源连接就能接管定位。系统控制器可以在前期承担路径执行，高级阶段把其租约交给玩家。每次切换均在 tick 边界提交并记录，禁止直接修改 Game Core 的算法分支。

从全知关进入未知地图关时采用新场景/纪元，不能把已泄露地图重新命名为“秘密”。撤权也清除 UI 缓存和可见图层；已被用户保存的信息无法撤回，应在内容设计中承认。

## 局部可玩性与反馈

未定位时玩家有车体固定图标、方向/键盘提示、授权测量、近距危险提示和暂停。自己的开火意图可在局部显示预测线，但必须标记预测，不能以真实全局弹道恢复真值位置。高级关卡撤键盘的是执行器权限，编辑器、暂停/重试和调试面板仍存在。

错误估计不会被修正成真值。提供测量时间/丢包/过期状态、玩家变量、协方差图、候选估计对比、已授权局部碰撞方向。详细真实轨迹对比只在显式结束后的评估视图，不能回灌活跃算法；Lab 的全知练习模式必须与正式测试分开标注。

## Campaign、Algorithm Lab 与 Arena 的复用

Campaign 加提示、模板和解锁规则；Lab 用同一部署与录制输入做参数扫描、轨迹图和版本比较；Arena 替换为服务器 Authority、强化沙箱和固定赛制。模式差别体现在内容、执行 profile、可见性与部署政策，不分叉 SDK 或 Core。

Lab 的“录制输入对比”不证明控制算法的闭环表现，闭环对比须重新运行各自世界。模板测试可给理想数据帮助理解，但正式关卡使用声明噪声和时延。服务器反复评分是潜在信息 oracle，需限制返回细节和请求频率；Arena 不提供活跃比赛逐 tick 真值误差。

## 替代方案、取舍与未决项

强制特定算法容易评分却抑制探索；使用轨迹误差、完成率、鲁棒性和预算评价，允许多种解法。过早多模块增加框架负担；先生成函数包装，C3 再解释完整 Contract。自动全知纠错体验平滑却抹去定位误差；用局部提示替代。

未决：每关误差/成功率阈值、传感器组合、物理参数、初学者需要多少 Python 教学。由玩法测试确定阈值，并使用多种参考算法检验可达性，不能把某一实现的输出当唯一答案。

## 验收条件

- C0–C2 可在不理解网络/JSON 的情况下完成，C3 起能复用前序 Python 文件。
- 每次撤权都先有可用替代输入、模板、局部反馈与测试夹具。
- 用至少两种合理方法完成噪声跟踪/定位关，不强制算法名称。
- LevelDefinition 无需改 Core 即可切换系统/玩家 Provider；未授权频道从 Router 到 UI 均不可达。
- 全知评估、局部观测和估计显示有明确标签，关卡不会通过效果/相机恢复真值。

## 所有关卡的说明准入

从本轮用户要求起，新关卡必须提供 [19](19_LEARNING_GUIDES_AND_SE3.md) 所定义的完整学习说明：算法文件、带类型签名、字段/单位、返回语义、调用与状态、合成自测及操作步骤。初学者只填算法，框架/导入/文件结构预先准备。当前 C1 已改为返回 NumPy SE(3) 元素，并由真实矩阵乘法消费；不能继续用未解释的自定义返回值替代矩阵学习目标。
