# 42 Navigation C5：已知地图全局路径规划

## 目的、范围与状态

稳定ID为navigation.c5，前置navigation.c4，复用Navigation独立工程的轮控、里程计、GPS/EKF与PathFollower。只新增玩家算法navigation/global_planner.py，不增加物理、传感器、动态障碍、未知地图或在线重规划。用户已确认下面合同，首版实现已接入；平台验收范围由 [ADR-0054](adr/0054-known-map-planning-preparation.md) 和最终报告区分。

## 地图与安全模型

正式引用maps/navigation_warehouse.yaml。可信场景准备从墙体联合包围盒解析唯一边界、原点和覆盖尺寸，按0.20m生成原始只读bool网格，墙体与格区域相交（含接触）即True，范围外为障碍。grid[row,col]的列向+x、行向+y，origin_xy为左下角格的左下角。格中心为origin+(col+0.5,row+0.5)*resolution；world_to_grid向下取整，grid_to_world返回中心，越界报错，禁止钳位。

OccupancyGrid冻结数组、原点和分辨率，底层不可重新打开写权限。程序没有World、宿主句柄、裁判参考路线或隐藏动态状态。玩家自行膨胀、生成邻居、搜索、后处理/重采样；框架只提供坐标转换。

车体从模型读取0.8×0.6m，外接圆0.50m、安全余量0.15m，总连续半径0.65m。ceil(0.65/0.20)=4：所有障碍和地图外区域横纵各4格完整方形膨胀；离散扩张横纵0.80m是明确的保守近似。规范膨胀只供裁判/UI，不能作为规划器辅助输入。路径不得进入或接触膨胀区域，数值容差不缩小障碍。

## 任务准备与复现

起点为公开[0,0]。按地图和seed选择安全自由格中心为终点：起终距≥5m，直连被规范膨胀障碍阻挡，八邻接最短安全栅格路长12–18m，禁止斜穿格角。长度仅用于选择任务，不限制玩家路径长度或最优性。原点按同一floor规则连接其所在格中心后搜索；每次扩展以米计轴向/对角代价。max_grid_cells=20000、max_search_nodes=20000及max_goal_attempts=128均在YAML：当前地图92×122共11224格，节点上限覆盖整图但保持有界，128限制不合条件的候选尝试。无任务明确报错，不降条件。

任务身份绑定地图、模型、参数、seed；重试保持相同任务，部署/测试不重新选点。传感器仍按run采样，编辑/部署时刻影响噪声位置；不保证任意准备时长具有相同成绩。

## 玩家接口与路径合同

```python
class GlobalPlanner:
    def __init__(self, map_data: OccupancyGrid,
                 robot_radius_m: float, safety_margin_m: float) -> None: ...

    def plan(self, start_xy: NDArray[np.float64],
             goal_xy: NDArray[np.float64]) -> NDArray[np.float64] | None: ...
```

start/goal为只读float64(2,)地图系绝对米制坐标。成功返回float64(N,2)，2≤N≤512，所有值有限；首尾与公开起终点距离≤1e-6m；每段长度>1e-6且≤0.10+1e-6m。中间点可不在格中心，必须由玩家完成后处理；全部节点和完整线段需安全。Authority给出错误类型和节点/线段索引，不修补结果。不额外限制最短路、转弯半径、自交或检查点。None表示正常无解；异常保留Python traceback。

## 准备、测试与正式部署

准备→规划（独立5秒墙钟）→Authority校验→冻结路径→周期模块初始化→固定边界激活。解释器/项目测试使用原初始化上限，规划器导入、构造、膨胀、搜索、后处理与结果完整往返均计入5秒。规划前不构造周期模块，清理测试加载的玩家模块缓存；规划后再清理项目模块并只向周期初始化交付Authority认可的静态路径。系统setup/reset不会再次规划或替换路径；规划结果在校验后冻结，周期初始化沿用独立初始化上限，不能作为另一规划结果提交入口。Manifest准备声明由同一关卡配置派生，缺少声明的旧工程需预览显式升级。

每个候选Worker只允许一次规划请求，绑定run、部署、任务及请求身份；准备控制帧采用独立preparation_version=1.0（不是可订阅Topic或通用Action），plan请求携带原始网格，响应显式dtype/shape/points_m或None；initialize只交付已校验路径。外部Supervisor看门狗可杀死死循环，Authority最终复核完整解码时间。迟到/重复/旧Worker结果拒绝，实时物理与UI不等待。期间底盘制动、不授予驱动；测试路径不进入正式裁判/视图。测试执行项目检查、真实任务规划/校验及既有短输入检查；正式部署新Worker重新规划，不复用测试结果或可变对象。独立无解测试可接受None，正式可达任务返回None失败。

周期控制沿用60Hz/4子步、30Hz编码器、2Hz GPS、10Hz模块、6tick提交及20ms声明准入；30/40ms实验性后端墙钟以 [41](41_RUNTIME_EXECUTION_PROFILES.md) 为准。PathFollower读取只读静态路径，结果经Twist参考/轮控制器/轮电压，不每批复制路径，不直接改物理。

## 规则、反馈与权限

首次正式轮电压生效起120仿真秒；规划不扣行驶时间，重部署不重置正式计时。无碰撞到终点≤0.35m、真实平移速率≤0.05m/s且|wz|≤0.10rad/s连续0.5秒通关，无终点yaw要求。碰撞/控制故障优先成功，最后允许tick可成功，其后超时。无路径、规划超时/异常/非法路径失败并制动；终局冻结。

公开地图/起终点、合法玩家路径、安全膨胀各有独立图层。Runtime只收原始网格；膨胀层是UI调试。显示车体/轨迹仍为玩家EKF。运行中授权宿主测得规划墙钟、路径长、计时、真实距终点和既有定位RMSE；真实折线追踪RMSE、最大偏离、实际路程仅终局，不参与通关，无顺序检查点。所有真值标量由Authority裁剪，不进入机器人Topic。地图覆盖仍为练习。

## 兼容、取舍与验收

新关YAML自动发现；参数/合同/权限均由配置声明，不按ID分派。四项已有算法、自建文件、revision/ledger/history保留；受管适配器/Manifest/Contract仅通过预览显式应用。空模板不含膨胀或搜索解。

首版采用静态方形膨胀和一次性准备任务，避免通用Action/中间件和连续重规划；保守网格牺牲狭窄可通行空间，但不改变用户确认的安全规则。验收至少用独立A*/Dijkstra、seed0/1/2、无解/非法/线段穿障碍/接触/超时/旧响应、计时/终局边界、无真值旁路及旧课程回归。原生和Firefox分别实际完成C4→C5编辑/测试/部署/通关/重试→C4，附截图与实测耗时；未通过项如实报告，不扩大预算或放宽阈值。

## 实现映射与可复查入口

| 职责 | 实现 |
| --- | --- |
| 原始地图/任务、私有参考距离、独立路径校验 | host/tankbot_host/global_planning.py、scene_definition.py |
| 玩家不可变输入 | sdk/python/tankbot/maps.py；只导出OccupancyGrid和坐标转换，不导出搜索/膨胀 |
| 准备阶段、Worker截止和正式激活 | planning_preparation.py、deployment.py、runtime/preparation_runner.py、supervisor.py、browser_authority.py、runtime-frame.js |
| 正式任务裁判与终局诊断 | planning_navigation.py；与C4复用PolylineMetrics，规则独立 |
| 授权元数据/状态与图层 | campaign.py、global-planning-view.js、campaign-ui.js |
| 参数/合同 | levels/navigation.C5.yaml；global-planning/preparation-task/level/workspace Schema |
| 测试参考 | tests/fixtures/planner_astar.py与planner_dijkstra.py独立搜索；共同几何后处理只存在测试目录 |

原生受控多seed自动化与真实界面属于不同验证层；真实Firefox流程可用tools/test_browser.py --scenario global-planning复现，所有路径均为隔离工程。具体命令、数据、截图和未覆盖平台见 [验收](reports/NAVIGATION_GLOBAL_PLANNING_VALIDATION.md)。
