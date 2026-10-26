# Weapons 渐进估计与文件树验收

历史范围：本报告记录当时的 C4 GPS/人工武器课程；当前 C4 已改为 C3 同款观测下的程序自瞄，C5 模型不变。当前证据见 [中心自瞄验收](CENTER_AUTO_AIM_VALIDATION.md)。

本报告记录 GPS/中心 Radar 版本的课程及显示修复基线。C5 后续已改为匿名装甲观测，当前接口与证据见 [30](../30_ARMOR_OBSERVATIONS.md) 和 [新验收](ARMOR_OBSERVATIONS_VALIDATION.md)；本报告历史数值不代表当前 C5 输入。

日期：2026-10-26。环境：Linux x86_64、CPython 3.14.4、Firefox 157.0.1、Node 22.22.1、Rust 1.99.1；浏览器使用锁定的 Pyodide 0.29.5。范围与确认模型见 [28](../28_WEAPONS_PROGRESSIVE_ESTIMATION.md)、[ADR-0035](../adr/0035-progressive-weapons-estimation.md)。

## 已验证行为

| 领域 | 验证 |
| --- | --- |
| 原三关 | C0–C2 YAML 未修改；保留冻结物理、初态、Radar 序列、权限、目标、评分、玩家输入/输出与模板文件基线；SDK 帮助只作兼容增量 |
| C3 | 原始车体系 r/theta 输入、极坐标输出、人工武器；显示/评分只使用同 tick 已公开自身位姿投影，不回退私有真值 |
| C4 | 前侧中央 GPS、12 m、穿墙、独立误差/丢失、独立可复现随机流；Radar 原序列不变；原地转向得到方向线索；人工装甲击杀 |
| C5 | 全向平移和持续自转经真实伺服产生；GPS/Radar 融合复用、预测/控制分文件、程序角加速度/单发、装甲击杀 |
| 接口 | GPS、极坐标类型的结构/帧/协方差/权限；C3 不可订阅 GPS；既有 AimInput 构造与地图字段兼容，新 target_rt 只读 |
| 迁移 | 新一/两模块图识别、切回 C1/C2、预览与确认升级、旧算法和旧控制器逐字保留、旧 revision/存档继续可用 |
| UI | tree 目录分支、多个任务文件高亮、文件选择/保存、真实 CodeMirror 编辑与 Test/Deploy；部署后自动收起、运行期锁定；无网页滚动 |

### C5 开发者预览修复复验

发现原开发者渲染只画统一矩形，未传递敌车自己的底盘显示模型；开发者图层复选框还错误地沿用玩家 `user_toggleable` 限制。物理层小陀螺已运行，本次修复没有改变速度伺服、碰撞、装甲或关卡参数。

修复后，受 grant 保护的 `DeveloperSnapshot.target_visuals` 提供每个动态目标的模型/轮组标定；普通 profile、PlayerViewSnapshot 与玩家 Runtime 输入不扩权。真实目标复用底盘绘制组件，位置和朝向继续经时间缓存插值，不用显示动画替代物理自转。开发者所有现有图层可独立切换，玩家限制不变。

真实 Firefox 页面使用独立 settings、progress 与 Workspace，在未部署程序的预览阶段验证：

| 模式 | C5 敌车模型 | 约 5 s 累计自转 | 位移 | 对照 |
| --- | --- | --- | --- | --- |
| 原生 | `radial-omni-x-v1` | 13.946 rad | 2.801 m | 玩家为差速；C2 仍为履带差速 |
| 浏览器 / WASM | `radial-omni-x-v1` | 13.813 rad | 2.781 m | 玩家为差速；C2 仍为履带差速 |

两种模式均采样 301 个显示帧，验证跨 ±π 的连续旋转、真实目标关闭/重开、切关重建和关闭开发者后 `UNAUTHORIZED`。结果及截图在 `.m1-cache/c5-developer-render/{native,browser}-ui.json` 和同目录 PNG；复验工具为 `tools/browser_developer_chassis.py`，需启动指定关卡的临时开发者服务后运行。

新增自动化覆盖独立敌车模型与两种玩家底盘的四种组合、开发者显示开关、普通玩家权限和多圈插值；`test_rendering.mjs` 14 项、`test_settings.mjs` 5 项通过。完整 Python 回归 173 项通过（105.020 s）；日志为 `.m1-cache/c5-developer-render/python-tests.log`。首次受限环境运行有 8 项 HTTP 测试因禁止创建套接字未能执行，在允许本机套接字的环境重跑后全部通过。文档/Schema 检查与 `git diff --check` 通过。

## 自动化结果

- Python：172 项完整回归通过（`weapons-redesign-regression.log`）；新增 9 项领域检查覆盖 GPS 几何/缺测/噪声、极坐标投影、可观测性、全向旋转和源码保护。
- Rust：17 项通过，涵盖既有运动、接触、炮台、弹道、装甲与生命边界。
- Node：38 项行为检查通过，包含新 tree 与计算属性提示，以及既有键位、日志、渲染和编辑阶段门。
- 同工具链原生/WASM：两种底盘各 600 tick、巡逻 1800 tick、角加速度/装甲 600 tick，以及新增全向小陀螺 600 tick 的完整私有快照相等；错误操作和缓冲上限继续拒绝。
- 构建：原生 Core、WASM release、编辑器/许可证及离线浏览器源码包完成。

日志与生成图片放在 `.m1-cache/`，不作为游戏资产提交。文档/Schema 检查是补充，不代替上述真实运行测试。

## 数值闭环与真实页面

参考实现仅位于测试工具中，使用 NumPy EKF 和有界预测状态；未提供给正式玩家，也不安装额外算法库。C3/C4 的 QA 操作者只读取授权估计、自身位姿和武器状态，通过与玩家相同的人工控制接口瞄准；C5 完全由玩家 Runtime 程序控制。

| 无头场景 | 通过 tick（60 Hz，起点 0） | 玩家 HP | 物理命中数 | XY RMSE |
| --- | --- | --- | --- | --- |
| C3 原始极坐标估计 + 人工接口瞄准 | 303 | 3 | 3 | 0.356 m |
| C4 GPS 融合 + 人工装甲瞄准 | 598 | 3 | 5 | 0.213 m |
| C5 融合 + 小陀螺预测/自瞄 | 1040 | 3 | 8 | 0.298 m |

两种 Runtime 的真实网页都逐关完成 CodeMirror 写入、文件树高亮、显式框架升级、测试、部署和通关；默认课程单元测试分别为 1/2/3 项。原始记录：[原生](weapons-redesign-native.json)、[浏览器](weapons-redesign-browser.json)。GUI 编辑期间世界仍推进，因此结果不要求与起点 0 的无头 tick/误差相同。

## 复现与限制

```bash
python3 tools/build.py --offline
python3 tools/build.py --wasm --release --core-only --offline
python3 tools/prepare_browser.py --offline
python3 -m unittest discover -s tests -v
cargo test --locked --offline
node tests/test_file_tree.mjs
node tests/test_sdk_hints.mjs
node tests/test_wasm.mjs
python3 docs/tools/check_design.py
python3 tools/export_profile.py --check --offline
git diff --check
```

真实 UI 使用 `tools/browser_m5.py --prepare-store PATH` 建立一次性源码/前置进度，再以该 store、独立 settings/save 和 `--player --level c3` 启动服务。Marionette Firefox 就绪后运行 `tools/browser_m5.py --url URL --port PORT --output PATH`；浏览器模式使用 `--browser-qa` 与 `?runtime=browser`。不要对玩家现用 Workspace 执行会写源码的 QA。

单 seed 参考解与通关证明技术可达性，不能证明教学效果或大规模公平性；未重新验证实体手柄、其他浏览器/OS。GPS 与 Radar 当前同期、零延迟，不宣称实现异步融合。跨硬件/工具链不保证位级确定性。旧已完成关卡记录继续有效，未自动重置用户进度。
