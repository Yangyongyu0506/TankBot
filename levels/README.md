# Level Plugins

本目录当前有公共C0、Weapons C1–C5与Navigation C0–C6共十三个独立YAML，是关卡专属配置的唯一来源。Weapons 课程见 [28](../docs/28_WEAPONS_PROGRESSIVE_ESTIMATION.md)，Navigation 首关见 [33](../docs/33_NAVIGATION_MOTION_CONTROL.md)。正式 Schema 为 [level.schema.json](../docs/schemas/level.schema.json)，架构和迁移说明见 [27](../docs/27_LEVEL_PLUGIN_ARCHITECTURE.md)。

## 编写与验证流程

文件名统一为 `<chapter_id>.C<n>.yaml`：章节使用 `metadata.chapter.chapter_id` 的小写标识，`C` 大写，保留当前课程编号。例如 `hello_robot.C0.yaml`、`weapons.C1.yaml` 至 `weapons.C5.yaml`、`navigation.C0.yaml`。
文件名只用于组织配置；加载、`--level`、前置关卡及存档继续使用 YAML 内稳定的 `metadata.id`（现有 `c0`–`c5`、`navigation.c0`–`navigation.c4`），不得因重命名而改变 ID 或玩家工作区。

1. 选择使用相同现有组件的配置作为起点，完整保留所需字段。metadata.id使用新稳定ID，order唯一且只负责展示/序列化；prerequisites引用已发现ID，必须无环，数组表示全部通关，不要求排在展示列表前面。不要修改已有稳定关卡的ID/顺序。
2. 在同一 YAML 中声明地图/初态/传感器/控制源、通信合同、权限、规则、诊断、教材与模板。当前C0–C5及Navigation C0–C3引用空旷教学场地，Navigation C4–C6引用仓储地图，见 [地图资产](../assets/maps/README.md)，地图可 inline，或仅引用 assets/ 内 `{walls: [...]}` 格式的地图文件；禁止 include 其他配置或脚本。
3. 机器人、传感器、规则、指标、可视化及模板必须使用已登记类型。调节现有参数不需要改引擎；未登记能力明确报错。当前一个玩家和可选的单个任务目标，不提前宣称支持 SLAM、机械臂或多机器人课程。
4. 先设置程序 inputs/outputs/actuators，再分别设置 View Policy 与 allowed_layers；初始显示和可切换项必须在显示权限内。默认保持旧用户图层偏好；需要按新关卡初始状态显示时可设 preserve_user_settings=false。
   运行中指标需同时声明 permissions.visualization.allowed_metrics 和 evaluation.live_feedback，且指标必须已在 evaluation.metrics 登记；标题、单位、小数精度和曲线容量全部由 YAML 配置。当前支持累计位置 rmse_m 和朝向 yaw_rmse_rad，未声明时不发布运行中诊断。
5. objectives.success 用 compare/all/any/not，终局数组顺序就是优先级。沿用声明的timer_start；没有live_feedback/task_feedback授权的诊断仅在终局发布。显示权限不改变评分，通用定位指标与路径追踪裁判指标分开。
6. tutorial.lesson.edit_files 声明文件树高亮的本关主要编辑文件（省略则从 functions 推导）；必须引用本 YAML 生成的玩家算法，不能标记系统管理文件。玩家算法文件不得加入 runtime.managed_files。YAML 只能选择引擎模板并提供字符串说明，不能提供执行脚本。默认入口、合同路径、类型、连线、预算和依赖均会校验。
7. 运行 `python3 docs/tools/check_design.py`、相关自动测试，以及 `python3 tools/export_profile.py --offline` 更新生成夹具；修改宿主代码后另运行 `python3 tools/prepare_browser.py --offline`。
8. 原生或浏览器以 `--developer --level <metadata.id>` 启动验收，使用独立 `--workspace-store`、`--settings-file` 和 `--save-file`。正式玩家仍按原存档解锁。无需修改 CLI choices、注册列表、UI 分支或 Level Manager。

加载器自动扫描 `.yaml` / `.yml`，浏览器启动器也调用相同扫描器并发布生成目录。文件错误显示完整 File/Path/Reason。不要手工编辑生成的 JSON 或用新编号文件替换旧关卡。零代码扩展测试只在临时目录创建额外配置，不进入正式目录。

## 已知地图规划关卡

使用objectives.global_planning配置分辨率、安全余量、任务搜索上限、路径合同与终点停稳；communication.runtime.preparation声明一次性5秒合同，Manifest同名字段由编译器派生，勿另写冲突副本。玩家只获得原始OccupancyGrid，裁判安全膨胀不经机器人接口公开。成功规则使用planning_complete，失败优先planning_collision/controller_faulted；不复用C4误差或检查点门槛。地图源仍为world.map资产引用，runtime四模块/模型/传感器不变，细节见 [42](../docs/42_NAVIGATION_GLOBAL_PLANNING.md)。

## 单位与受支持范围

位置为 m、角度为 rad、速度/角速度为 m/s 和 rad/s，炮台程序输入为 rad/s²；协议消息和端口名字保持现状。clock 中物理、子步、基础传感器和算法频率分离；基础传感器采样率须与现有 Core 一致，Radar 必须整除物理/基础传感器率。规则用仿真 tick，渲染继续独立插值。

公共标定用受限 `source` 引用模型尺寸/武器参数，不能引用敌方当前位姿或巡逻路径。教材中的数量/频率/噪声可使用公开占位符，避免修改参数后出现陈旧说明。所有修改都应验证原玩家源码兼容与不覆盖 Workspace。

新增已实现组件：`intercepted_gps` 提供地图系车头 fix；巡逻 `spin_rate_radps` 只允许全向底盘且受角速度上限限制。模板组件包括 polar_tracker、fusion_tracker、raw_sensor_adapters、target_prediction、polar_auto_aim、predictive_aiming_adapter 及对应 contract_tests；每个关卡依自己的 YAML 组合，不依赖关卡 ID 分支。当前正式关卡不启用 intercepted_gps；该兼容组件按同期采样工作，未实现任意异步融合。Navigation C2–C6使用独立的自身gps实例。

`armor_detector` 提供最近可见装甲的匿名 base_link 极坐标，使用 `armor_detections@1`，最多两行；对应模板为 armor_tracker、armor_tracking_adapter、armor_contract_tests。当前 C5 用这些组件替换 GPS/中心 Radar。C4 则复用 C3 的 polar_tracker/raw_sensor_adapters，并组合 predictive_aiming_adapter、target_prediction 和 polar_auto_aim；无装甲时构造器获得 (0,3) 空矩阵，不要求 yaw。yaw_rmse 可声明 `period_rad`，加载器验证该周期确实保持底盘装甲布局；不允许用错误周期隐藏估计误差。完整接口和教学约束见 [30](../docs/30_ARMOR_OBSERVATIONS.md)。

通用底盘在 `config/chassis/*.yaml` 定义质量/惯量、轮组、伺服/阻力、限制、装甲/GPS安装与外观，由 `config/game.yaml` 统一加载。`motion.chassis` 选择底盘，`armor: {source: chassis_profile}` 启用其装甲；不要在关卡或教材中重复安装数值。共享引擎模型是经 ADR-0036 允许的组件资产，不允许关卡任意 include 其他文件。C5 当前全向车体 0.42×0.42 m、装甲中心 ±0.21 m；完整约束见 [29](../docs/29_CHASSIS_PROFILES.md)。

传感器正式源现显式声明 id、robot_id、mount、period_ticks、random_stream 与 topic/schema/frame_id。旧 update_hz 和内部适配字段在加载时生成并校验；不要复制两组矛盾参数。底盘 profile 2.0 为完整模型，世界配置不再手填重复的质量/伺服/轮组数值。关卡首次解析后缓存 ResolvedScene，重试共享定义而重新创建运行状态，详见 [32](../docs/32_RESOLVED_SCENE_AND_COMPONENTS.md)。

scaffolding 可声明 workspace_scope（小写字母开头，后续为小写字母、数字、下划线或连字符，最长 48 字符），为默认项目指定稳定分组；省略保持原 campaign 项目。跨 scope 直接 unlock 拒绝，启动器通过 select_workspace 选库，原源码与历史不清空。

Navigation 组件：world.weapons_enabled=false、objectives.target=null 支持无武器/无敌车；玩家 drive=wheel_voltage 选择差速底盘 motor 参数，输出为 /robot/wheels/cmd_voltage。objectives.command_sequence 声明 type=twist_sequence、topic=/robot/cmd_vel、repeat 和 duration_ticks/twist 组成的 segments，参考指令方向为 Authority→玩家。各段时长对齐控制周期、总时长匹配 time_limit_s；timer_start=first_control_commit。新增事实 sequence_complete、controller_faulted、origin_distance_m、path_length_m，以及参数 max_origin_distance_m/min_path_length_m。两个运动显示指标分别受 allowed_metrics 授权；不按关卡 ID 分支，完整设计见 [33](../docs/33_NAVIGATION_MOTION_CONTROL.md)。

Navigation C1（navigation.C1.yaml）复用 Navigation C0 的控制器，新增 wheel_odometry/wheel_odometry_adapter；evaluation.source=player_pose 明确评估选中的自身位姿候选。规则可比较 rmse_m/yaw_rmse_rad，live_feedback 兼容单对象或多指标数组，分别受 allowed_metrics 授权。control_feedback 的图表、周期与容量声明在 visualization，信号必须获 allowed_control_signals 授权；不能借调试曲线发布真值。完整接口见 [34](../docs/34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md)。

Navigation C2（navigation.C2.yaml）复用控制器/里程计，组合 ekf_localization/ekf_localization_adapter。wheel_encoder 可声明 velocity_stddev_radps、gain_error_min/max、position_model=integrated_rate_noise，转用 Python 测量后端；旧无误差实例仍用 Rust。gps 提供 position_fix2d@1，period_ticks=30 与预测周期对齐，独立命名随机流；当前仅中心安装、零偏置/丢失/延迟和无遮挡，不接受未实现模型。传感器参数由正式 Schema 与领域校验约束。

evaluation.module_id 固定主位姿评分，reference_module_id 指定独立对照；两者必须是已声明且不同的 pose 发布者。live_feedback 的 reference_metric/reference_label/reference_color 可添加与主指标共轴的对照曲线，指标仍各自受 allowed_metrics 授权。View Policy 的 pose_estimate_channels 配置授权候选列表，对应 pose_estimates 图层与 player_pose_candidates 数据源；gps 使用 local_observation，pose_covariance 使用 selected_pose。gps_history_points、trail_points 控制容量，pose_labels 配置来源显示名。command_sequence 可按实际路程和估计阈值验收，无需声明未使用的终点距离门槛。完整课程见 [35](../docs/35_NAVIGATION_GPS_LOCALIZATION.md)。

当前十三关进度为公共c0后同时开放Weapons C1和Navigation C0，各主线内部保持原依赖。新增插件时，公开catalogue自动输出prerequisites/order/description，关卡树据此生成节点和实线；不要手工维护UI关系。新档从无前置入口开始，已完成集合不要求全局前缀，完整规范见 [36](../docs/36_BRANCHING_PROGRESSION.md)。

Navigation C3 的 `objectives.waypoint_route` 组合公开目标与私有到点/停稳评价，使用 `waypoints_complete` 事实。`permissions.data_access.references` 仅授权轮电压驱动的 `/robot/cmd_vel` 参考，`actuators` 继续授权实际电压；禁止双发布源或与速度伺服混用。waypoint_goal@1 只向程序提供当前目标，`waypoints` 图层独立授权公开路线/任务状态，不能补画真值车体。接口、边界与零代码复用限制见 [37](../docs/37_NAVIGATION_WAYPOINT_CONTROL.md)。

模块Contract.execution.budget_ms只声明准入额度，整图求和与冻结profile的module_declared_budget_cap_ms比较；整批往返另用后端batch_wall_deadline_ms，固定6tick门不因墙钟增加而变化。配置兼容与诊断以 [41](../docs/41_RUNTIME_EXECUTION_PROFILES.md) 为准，不能在关卡中借改预算扩大权限。

## 连续路径组件

Navigation C4 的 `objectives.path_tracking` 声明 `continuous_path` 任务：生成参数、顺序检查点、停稳与参考限制在同一YAML，评分阈值只在 `objectives.parameters` 保存一份。裁判事实 `path_complete/path_collision/path_deviation_exceeded/tracking_rmse_m/max_deviation_m` 供声明式终局规则使用。

`warehouse_search_round_v1` 在可信场景准备阶段运行，无关卡ID分支。解析后路径身份绑定地图、完整车体、初态、参数和seed，部署/测试/重试不重选；失败有界退出。`path_reference` 静态输入必须在 `permissions.data_access.task_inputs` 显式授权；`path_tracking` / `path_tracking_adapter` 模板复用玩家EKF和轮电压控制器。

`path` 与 `checkpoints` 图层使用 `task_reference`，显示状态与算法输入独立。`permissions.visualization.task_feedback` 单独授权live的 `goal_distance_m/checkpoints` 与terminal的追踪指标，运行中不额外提供真实偏离误差。Schema详见 [path-tracking.schema.json](../docs/schemas/path-tracking.schema.json)，默认参数依据和编写边界见 [40](../docs/40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)。

## 先验地图下的局部静态避障

C6仍使用global_planning与同一规划准备合同；objectives.local_navigation配置独立命名随机流、方障碍尺寸/间距、生成上限和输入年龄。公开scene.walls保持先验；可信解析的private_obstacles只交给物理/扫描及私有可达性校验。distance_scan经SensorScheduler采样。local_navigation_adapter在原导航模块内组合PathFollower与LocalController，三个输入optional，缺测主动零参考。地图扫描、车体系扫描和开发者私有矩形是独立图层。详见 [43](../docs/43_NAVIGATION_LOCAL_AVOIDANCE.md)。
