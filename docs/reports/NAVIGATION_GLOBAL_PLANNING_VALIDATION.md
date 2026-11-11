# Navigation C5 已知地图规划验收（2026-11-11）

本次从干净的 HEAD `3531d80` 开始。关卡采用 `navigation.c5` 和现有 Navigation 工程，通关 `navigation.c4` 后解锁。仓储地图解析为 92 行 × 122 列的只读原始网格。玩家提交的路径先经过 Authority 整段安全校验，再交给已有的定位、追踪与轮控链。参考搜索源码位于测试目录，正式模板提供类型、参数和待实现的 `plan`。 [关卡配置](../../levels/navigation.C5.yaml) · [设计合同](../42_NAVIGATION_GLOBAL_PLANNING.md)

## 原生闭环和真实界面

测量环境为 Linux x86_64、AMD Ryzen 9 8945HX、CPython 3.14.4、Firefox 157.0、Pyodide 0.29.5。原生闭环使用受控推进与真实 Core/Supervisor，真实界面运行使用两种后端各自的页面调度。规划时间为单次完整往返的墙钟观测。周期最大值来自该次正式行驶的 Runtime 往返统计。

A* 和 Dijkstra 各在 seed 0、1、2 完成原生闭环。三组终点分别为 `(9.7, -4.5)`、`(-9.3, 4.3)`、`(-7.1, -7.3)` 米，裁判的最短安全栅格距离分别为 13.170、13.156、12.281 米。每个终点满足绕障条件，同一配置重试保留任务身份。六次正式尝试均通关，周期截止故障数均为 0。

| Seed | 算法 | 测试规划 ms | 正式规划 ms | 周期往返最大 ms | 行驶仿真秒 | 追踪 RMSE m | 最大偏离 m |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | A* | 29.46 | 32.69 | 10.34 | 38.62 | 0.150 | 0.343 |
| 0 | Dijkstra | 40.50 | 41.64 | 8.56 | 38.43 | 0.152 | 0.347 |
| 1 | A* | 32.85 | 31.91 | 10.63 | 44.37 | 0.087 | 0.188 |
| 1 | Dijkstra | 39.39 | 42.25 | 11.16 | 44.28 | 0.087 | 0.188 |
| 2 | A* | 32.21 | 30.84 | 3.83 | 35.78 | 0.196 | 0.564 |
| 2 | Dijkstra | 39.12 | 41.87 | 3.76 | 36.02 | 0.195 | 0.564 |

真实界面从已完成前置课的隔离 C4 工程进入 C5，经编辑和保存、升级预览和显式确认、完整规划测试、独立 Worker 部署、通关、重试，再回到 C4。两种后端均完成整个流程。Pyodide 覆盖两个算法和全部三个 seed，原生界面覆盖 seed 0 的 A*。原有轮控、里程计、EKF、PathFollower 及自建文件逐项保留。重试验证新 run 身份、同一任务、待规划状态和已保存的 revision。旧 revision 可读性和 ledger 保留由工作区回归另行核对。

| 后端 | Seed | 算法 | 测试规划 ms | 正式规划 ms | 周期往返最大 ms | 行驶仿真秒 | 追踪 RMSE m | 最大偏离 m | 记录目录前缀 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 原生 | 0 | A* | 26.94 | 30.08 | 5.23 | 39.52 | 0.144 | 0.354 | `e181b4cf` |
| 原生 | 0 | A*（含异常恢复） | 27.51 | 27.03 | 8.07 | 38.95 | 0.162 | 0.309 | `08965a54` |
| Pyodide | 0 | A* | 80.00 | 77.00 | 19.00 | 39.12 | 0.145 | 0.300 | `00f609b8` |
| Pyodide | 0 | A*（含异常恢复） | 83.00 | 74.00 | 24.00 | 40.50 | 0.170 | 0.373 | `7e02a379` |
| Pyodide | 0 | Dijkstra | 96.00 | 104.00 | 19.00 | 39.00 | 0.145 | 0.295 | `24a7a282` |
| Pyodide | 1 | A* | 72.00 | 74.00 | 33.00 | 42.93 | 0.093 | 0.231 | `8574ecd4` |
| Pyodide | 1 | Dijkstra | 99.00 | 97.00 | 19.00 | 42.93 | 0.093 | 0.231 | `42995bf9` |
| Pyodide | 2 | A* | 76.00 | 81.00 | 25.00 | 35.98 | 0.190 | 0.567 | `98b41cb1` |
| Pyodide | 2 | Dijkstra | 102.00 | 105.00 | 27.00 | 36.13 | 0.191 | 0.567 | `34c21b9c` |

各行正式行驶都通关，周期截止故障数均为 0，终点连续停稳 30 tick。运行中验证三图层独立切换和 EKF 位姿来源，终局验证真实追踪诊断可见。seed 2 合法路径约 11.21 米，最大偏离约 0.57 米，按 C5 的无碰撞到达与停稳规则成功。自动化另覆盖最后一个允许 tick 成功，以及同 tick 碰撞或控制故障优先结算。

## 异常和兼容性

两种后端的真实界面各注入四个规划测试负例。`None` 得到 `PLANNING_NO_PATH`，`float32` 得到 `PLANNING_PATH_DTYPE`，构造器异常显示 `navigation/global_planner.py:3`，构造器死循环触发独立 5 秒截止并得到 `PLANNING_TIMEOUT`。每次负例均核对正式计时尚未开始、正式路径尚未冻结。恢复合法源码后重新测试、部署和通关。 [Pyodide 异常恢复截图](assets/navigation-global-planning/pyodide-planning-errors.png)

自动化覆盖只读输入和坐标边界、形状与精度、非有限数值、首尾和间距、超过点数上限、端点合法但线段穿越或贴边、生成上限、旧 Worker 与超时响应、正式无路径后制动和终局冻结。运行权限测试核对原始网格输入和裁判膨胀图层分离。地图覆盖练习沿用已有进度隔离，无法满足绕障条件的空地图有界拒绝。 [几何用例](../../tests/test_global_planning.py) · [准备协议用例](../../tests/test_planning_preparation.py) · [闭环与工程迁移](../../tests/test_navigation_global_planning.py)

实现迭代中的首次原生界面尝试在升级提示断言处停止，尚未提交规划请求。随后由关卡编译生成受管 Manifest 准备声明，C4 工程进入 C5 时显示升级预览。成功记录已复验确认、部署和往返。首次统一回归暴露了旧目录断言和新关地图覆盖期望，已更新相应测试。回环和 IPC 测试在获得本机回环权限后重跑，仍使用离线配置和隔离数据。

## 检查与复现

统一检查通过，包含 84 项前端用例、376 项 Python 用例、18 项 Rust 测试、文档与 Schema 校验、生成配置一致性检查。

```bash
python3 tools/check.py --offline
python3 tools/prepare_browser.py --offline
npm run test:wasm
python3 tools/test_browser.py --mode both --scenario global-planning --offline --seed 0 --planner astar --planning-faults
python3 tools/test_browser.py --mode browser --scenario global-planning --offline --seed 0 --planner dijkstra
python3 tools/test_browser.py --mode browser --scenario global-planning --offline --seed 1 --planner astar
python3 tools/test_browser.py --mode browser --scenario global-planning --offline --seed 1 --planner dijkstra
python3 tools/test_browser.py --mode browser --scenario global-planning --offline --seed 2 --planner astar
python3 tools/test_browser.py --mode browser --scenario global-planning --offline --seed 2 --planner dijkstra
python3 tools/tankbot.py --level-tree --offline --save-file /tmp/tankbot-c5-no-save/progress.json
git diff --check
```

WASM 检查通过，覆盖共用 JSON ABI、武器及运动快照、仓储地图墙体接触和错误输入边界。CLI 核对目录中的 12 课和 C4 到 C5 的前置关系。浏览器脚本在独立设置、进度、Workspace、回环端口与 Firefox profile 中执行。运行数据位于 `.m1-cache/navigation-c5-qa/`，原生受控结果为 `native-multiseed.json`，页面结果为 `browser/<mode>/<run>/result.json`。

截图来自含异常恢复的 seed 0 A* 流程。 [原生行驶](assets/navigation-global-planning/native-running.png) · [Pyodide 行驶](assets/navigation-global-planning/pyodide-running.png) · [Pyodide 结算](assets/navigation-global-planning/pyodide-finished.png)

测量范围限于上述本机环境与测试样本。后端周期 profile 仍处于 experimental，30/40 ms 截止、20 ms 声明总额与 `activation + 6 tick` 提交边界继续由现有 profile 执行。路径准备使用独立的 5 秒墙钟截止。实验之外的硬件、浏览器与玩家实现仍需独立测量。 [运行配置规范](../41_RUNTIME_EXECUTION_PROFILES.md) · [ADR-0054](../adr/0054-known-map-planning-preparation.md)
