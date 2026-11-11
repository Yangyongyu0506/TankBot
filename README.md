# TankBot

TankBot 将二维坦克运动、机器人算法学习与多文件 Python 编程结合。玩家通过传感器和自己的算法重建世界认知。

当前为可玩的本机原型：Rust/Rapier2D 权威物理、差速/四轮径向全向底盘、Python SDK/Runtime、固定 tick 提交、授权视图和 CodeMirror 多文件编辑部署。原生模式与 Rust/WASM + Pyodide 双 Worker 浏览器模式共享仿真及课程语义。

现有公共 C0、Weapons C1–C5 和 Navigation C0–C5 共十二关，由 YAML 自动发现。Weapons 覆盖坐标变换、目标滤波、预测自瞄和小陀螺装甲；Navigation 已有轮电压控制、里程计、GPS/EKF、航点位置闭环、仓储连续路径追踪和已知地图全局规划。Weapons C2有授权滤波回放试点，另有耗时诊断和可恢复项目备份；完整Algorithm Lab、局部避障、建图及Arena尚未实现。应用配置为2.1；当前实现、历史验证和未来计划见 [文档索引](docs/README.md)、[2026-11-10核对](docs/reports/DOCUMENTATION_STATE_SYNC_20261110.md)。

## 构建与运行

需要 Rust **1.99.1**、Python **3.11+**（本机实测 3.14.4）、Node.js **22+** 与 npm；WASM 探针另需 `wasm32-unknown-unknown`。编辑器构建会自动安装锁定的 npm 依赖，游戏启动器会自动准备 Python 依赖：

```bash
python3 tools/build.py
python3 tools/tankbot.py serve
```

首次启动检查 `requirements.txt`：缺少 NumPy 等依赖、版本不符或导入失败时，自动创建 `.m1-cache/python/` 下的专用环境、下载并安装，再继续运行原命令；宿主没有 pip/ensurepip 也可引导。系统 Python 和已有虚拟环境保持原样，玩家无需手动激活。后续启动复用缓存；完整缓存可用 `--offline`，安装失败后重新运行同一命令重试。说明见 [首次运行设计](docs/21_DEPENDENCY_BOOTSTRAP.md)。

打开 `http://127.0.0.1:8765`。差速：W/S 前后，A/D 转向。全向：W/S 前后，A/D 横移，Q/E 转向；启动时选择：

```bash
python3 tools/tankbot.py serve --chassis omnidirectional
python3 tools/tankbot.py serve --developer --view weapons-practice
python3 tools/tankbot.py headless --ticks 600 --robot-demo
```

## 教学关卡（M4）

```bash
python3 tools/tankbot.py serve --level c0
# 已构建 WASM 并 prepare_browser.py 后也可使用浏览器模式：
python3 tools/tankbot.py browser --level c0
```

在顶部或「任务」面板打开「关卡路线」，选择节点查看简介和具体前置，再点击「开始本关 / 重试」。公共 C0 通关后，可任选 Weapons 或 Navigation 主线并交替推进。C0 先移动至少 1 m、转动车体至少 0.5 rad，并命中可见靶标。C1 隐藏敌车，F2 打开编辑器，完成自动生成的 `perception/transforms.py`，返回 `NDArray[np.float64]` 形式的 4×4 SE(3) 矩阵，测试并部署，利用目标估计瞄准命中。C2 保留该矩阵函数，追加 `perception/tracker.py`；处理带噪声和 10% 丢失的雷达，跟踪巡逻敌车，保持存活并击中三次使敌车 HP 归零即可通关。

前三关保留系统自定位和公开地图；C0 可人工驾驶，C1/C2 锁定底盘并保留人工炮台与开火。Radar 是车体系局部观测，地图上的目标标记来自玩家 Python；Weapons C1–C5 默认显示炮弹，可在图层设置中开关；真实敌车和命中特效位置仍隐藏，Python 输入权限不变。C2/C3 显示双方 HP，以及运行中的累计位置 RMSE、有效样本数和变化曲线；编辑器也显示同一指标。测试不计入、重复部署不清零，重试重新累计。通关或点击「结束本次尝试」后关闭玩家程序并冻结最终误差报告；物理与已有弹丸继续运行。重试建立新场景，新关只补缺失文件，已有源码保留；保存的草稿须重新 Test/Deploy。Weapons 内部仍按 C1 → C2 → C3 → C4 → C5 解锁，Navigation 内部按 C0 → C1 → C2 → C3 → C4 → C5 解锁；两条首关均只依赖公共 c0。通关后列出所有新开放节点，允许重玩，不强制自动进入下一关。开发者仍可自由练习。

F1 或编辑器中的「关卡说明 / 类型」可随时查看每关步骤、输入输出签名、SDK 字段/单位、Python 速查与交互矩阵实验；悬停及 Ctrl+Space 提供类型提示。新模板显式标注变量和返回类型。旧工作区可预览模板升级并选择系统脚手架，已有算法默认保留。原生 NumPy 随首次启动自动准备；浏览器运行 `prepare_browser.py` 准备锁定的 Pyodide/NumPy 资源。

旧工作区点击「测试快照」时，若运行框架仍为旧版，会先打开更新预览；确认「保留算法，更新框架并继续测试」后继续。已有算法文件排除在替换计划之外，旧运行文件可从历史版本恢复。测试检查语法/导入/接口、项目单元测试和默认 6 批授权传感器试运行；C1 包含 SE(3) 样例，不要求先通关。当前快照通过测试后部署按钮才会亮；旁边会说明等待、失败或重新测试的原因。

C0/C1/C2 分别限时 **60/60/120 仿真秒**。C0 首次有效人工操作起算；C1/C2 首次成功部署玩家程序起算，之前的编辑和测试不计时。正式运行期间锁定代码编辑器，须先点击任务页的「结束本次尝试」，或「开始 / 重试」重置关卡，再修改代码；倒计时不因算法错误暂停。C2 玩家与敌车同为 3 HP，反弹自伤也扣血，玩家死亡或超时判失败。详见 [关卡规则与参数](docs/25_ATTEMPT_RULES_AND_CONFIGURATION.md)。

完整模型和接口见 [M4 设计](docs/18_CAMPAIGN_DESIGN.md) 与 [学习说明设计](docs/19_LEARNING_GUIDES_AND_SE3.md)，验证见 [M4 报告](docs/reports/M4_VALIDATION.md) 及 [SE(3) 学习工具验收](docs/reports/LEARNING_VALIDATION.md)。

默认炮台 J/L 转动，空格或按钮单发（长按不连射）。开发者自由试验场的估计视图隐藏真实弹丸，保留炮台与武器局部反馈；`--developer --view weapons-practice` 明确授权练习图层。Python 输入权限不增加。`--robot-demo` 使用独立的 [weapon_demo.py](examples/robot/weapon_demo.py) 控制炮台/开火，人工底盘仍可用；对应人工武器入口会拒绝。想观察程序控制可运行 `python3 tools/tankbot.py serve --developer --robot-demo --view weapons-practice`。

查看完整关卡依赖树及存档中的通关状态，无需启动游戏：

```bash
python3 tools/tankbot.py --level-tree
# 查看另一份存档
python3 tools/tankbot.py --level-tree --save-file /path/to/progress.json
```

树形输出标出已通关、可挑战、未解锁、当前关卡和缺少的前置，依赖直接来自关卡 YAML。命令只读存档，不创建设置、工作区或仿真进程；没有存档时显示新玩家预览。游戏内可点击顶部「关卡路线」查看交互式依赖树。

启动时可用 `--map open_large` 覆盖关卡地图（例如 `python3 tools/tankbot.py serve --level c0 --map open_large`），`--list-maps` 列出资产。顶部「地图预览」显示全景；开发者可浏览全部地图。覆盖地图作为自定义练习；路径课程仍校验安全/长度/绕障约束，无解会明确拒绝。练习不计正式通关，重试/切关继续沿用；省略参数重启服务恢复默认。详见 [地图覆盖与预览](docs/31_MAP_OVERRIDE_AND_PREVIEW.md)。

地图集中在 [assets/maps](assets/maps/README.md)：Hello Robot / Weapons 共用 12×8 m 空旷场地，另提供大型空旷、绕行、仓储布局和原试验场。Navigation C0–C3 沿用空旷教学场地，C4 正式引用仓储布局，裁判按地图与 seed 自动生成安全路径；布局预览及引用方式见目录说明。

完整底盘模型（质量、惯量、轮组、伺服、阻力、限制与外观）在 [config/chassis](config/chassis/)；世界时钟、求解器、武器与平台参数在 [config/game.yaml](config/game.yaml)。统一传感器实例及不可变场景的接口见 [32](docs/32_RESOLVED_SCENE_AND_COMPONENTS.md)；各关的地图组合、传感器、权限、规则、合同和教材分别在 [levels/](levels/README.md) 的独立 YAML 中，缺项报错，不补隐藏默认值。底盘只能在场景启动时选择。可在网页中保存、测试并部署 Python 项目；编辑与部署分离，成功部署不重置物理世界。示例算法在 [examples/robot](examples/robot/localization/odometry.py)，支持多文件 import，启动不会改写源码。

## Navigation 连续路径追踪

通关 Navigation C3 后解锁 `navigation.c4`。复用已保存的轮控、里程计和 EKF，只新增 `navigation/path_follower.py`：输入只读 `float64 (N,2)` 完整地图系路径和玩家 EKF 位姿，输出非负前进的 `Twist` 参考，再由轮控制器执行。仓储路径由裁判自动搜索、圆角和重采样，重试/部署保持相同路径。

```bash
python3 tools/tankbot.py serve --level navigation.c4
# 开发者预览仍可显式添加 --developer
```

120 仿真秒内连续追踪、按序经过检查点并在终点停稳；碰撞、偏离超限或控制故障立即失败。路径与检查点图层可独立开关，主反馈是距终点的欧式距离；真实追踪误差只在终局报告。教材、参数和接口见 [40](docs/40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)。首次进入须预览受管框架升级，原算法及历史保留。

## 设置、玩家存档与开发者图层

点击顶部「设置」或默认 **F10** 打开设置页面，× 关闭。可修改键盘绑定、恢复默认键位，并切换开发者模式；编辑器默认 F2、说明默认 F1，也可改键。设置界面打开期间暂停驾驶与开火。模式切换会重新开始关卡，先保存代码并等待测试/部署结束。

首次创建 `userdata/settings.yaml`，保存键盘映射、开发者开关和图层选择；默认模板在 [config/settings.yaml](config/settings.yaml)。玩家通关记录在 `userdata/progress.json`，刷新或重启后保留；首次只开放公共 C0，完成后同时开放 Weapons C1 和 Navigation C0，CLI/API 同样按各节点前置检查存档。可以用 `--settings-file /path/settings.yaml --save-file /path/progress.json` 指定自己的文件。损坏或未知版本的文件报错并保留原件。

开发者模式通过设置开关或 `--developer` 开启，`--player` 切回玩家模式。「图层」页可独立显示/隐藏真实车体、目标、弹丸、玩家估计、轨迹、Radar、IMU、坐标系、速度箭头与碰撞外形，并选择消息查看器中的 Topic。开发者练习不计入玩家进度；关闭模式后撤回真值并返回玩家关卡。玩家只列出本关授权图层，Python 算法的数据权限保持关卡约定。设计和单机信任范围见 [22](docs/22_SETTINGS_MODES_AND_PROGRESS.md)，实测见 [验收报告](docs/reports/SETTINGS_VALIDATION.md)。

## 手柄操控

两种运行方式均接入浏览器 Gamepad API。连接标准手柄后点击游戏页面，按任意手柄键，再松开摇杆和按键；顶部显示连接状态，「驾驶」页可启停或选择手柄。

| 操作 | 默认映射 |
| --- | --- |
| 驾驶 | 左摇杆；差速横轴转向，全向横轴横移 |
| 车体左/右转 | LB/RB（L1/R1） |
| 炮台旋转 | 右摇杆横轴 |
| 单发 | RT（R2），长按不连发 |
| 打开/收起编辑器 | Start（Options/+） |

摇杆控制目标速度比例，松开后主动制动。键盘按住时按执行器优先；编辑、切出页面或断连会清除手柄目标，返回后需先回中。程序接管的执行器不接受人工指令。映射、方向、死区和速度均在 `config/game.yaml` 的 `view.gamepad`；非标准手柄可显式配置索引。远程网页需 HTTPS，本机 localhost 可用。设计及硬件验证边界见 [手柄设计](docs/20_GAMEPAD_INPUT.md) 与 [验收报告](docs/reports/GAMEPAD_VALIDATION.md)。

`tools/build.py` 先从 YAML 生成 Rust/Node 测试夹具，再构建 Rust Core，并自动检查 `package-lock.json` 和已安装的 npm 依赖：缺失或版本不匹配时执行锁定安装，然后每次重新构建编辑器及许可证文件。`--web-only` 只修复/构建编辑器，`--core-only` 用于无需 Node.js 的无头核心构建；`--offline` 要求 Cargo 与 npm 依赖已在本机缓存。缺少 Node.js/npm 时会报出安装要求，不会假装 UI 已构建。脚本优先使用正常 Cargo；未安装时可使用本机已有的 `.tools/rust` 工具链与 `.tools/cargo` 缓存。这些目录被忽略，不是分发依赖。常规 Rust 环境也可直接 `cargo build --locked`，但它不生成编辑器资源；更新 YAML 后先运行 `python3 tools/export_profile.py` 同步 Rust/Node 测试夹具。

## 浏览器单机（M2 本机验收）

同一 Rust Core 与 Python SDK/Authority 在浏览器两个 Worker 内运行；启动器提供静态资源、只读启动种子与版本化 Workspace 存储，不在服务端执行玩家 Python 或仿真。

```bash
python3 tools/build.py --wasm --release
python3 tools/prepare_browser.py          # 首次下载锁定版本/摘要的 Pyodide
python3 tools/tankbot.py browser --chassis omnidirectional
```

打开 `http://127.0.0.1:8765/?runtime=browser`，操作与原生模式相同。首次启动会加载两个 Python 解释器；Test/Deploy 时额外启动候选 Worker，当前机器人继续运行。玩家源码在页面中编辑并显式部署；修改 SDK/Authority 源码须重新 prepare bundle 并刷新。`--view weapons-practice` / `--robot-demo` 同样适用。资源准备后可运行 `python3 tools/prepare_browser.py --offline`；底盘参数来自 config/chassis/*.yaml，世界时钟、求解器与武器参数来自 config/game.yaml，课程组合来自 levels/*.yaml。两个 loopback 端口默认 8765/8766，不能与原生服务同时占用同一端口。

已验证 Linux / Firefox 157，其他平台仍待验证。Runtime origin 的 CSP 限制跨 origin 网络/嵌套 Worker，仍没有浏览器硬内存/CPU/存储额度。服务器沙箱、Arena 与第三方代码上传未开放。详细流程及代价见 [浏览器设计](docs/16_BROWSER_RUNTIME.md)。

## 多文件编辑与部署（M3）

游戏界面固定在视口内，无需滚动网页。准备阶段或本局结束后，点击顶部「代码编辑器」或按默认 **F2** 打开铺满窗口的 Workspace；再次按对应快捷键或点击右上角 **×** 收起。草稿、光标与选中文件会保留。左侧按 tree 命令风格显示目录树，高亮本关主要编辑文件，长文件名可在侧栏内横向滚动。Workspace 支持 Python/JSON 编辑、Vim、文件切换、新建文件、Ctrl/⌘S 或 `:w` 保存。依次点击 **测试快照 → 部署已测试版本**；部署成功后自动收起编辑器，焦点回到游戏画布，Space 按本关权限发射；正式运行中 F2、F1、手柄 Start 和日志源码链接均不能重开编辑器，结束或重试后恢复。测试或候选启动失败时保留编辑器、错误日志和当前机器人。历史部署可显式回滚，产生新 Runtime 并清空算法状态，物理世界继续运行。编辑器焦点不会把 W/J/L/空格传给坦克。

默认编辑库保存在 `userdata/workspaces/<项目标识>/`，与 `userdata/settings.yaml` 和 `userdata/progress.json` 一起管理。源码以版本化 JSON 快照保存，模板 ledger、历史版本和测试/部署归档均在项目目录中，跨刷新与重启保留。备份整个 `userdata/` 即可保存个人数据。

首次使用新路径时自动复制旧 `.m1-cache/workspaces/` 中的各个默认项目，验证历史快照后原子发布，旧目录保留为备份；目标已有项目时不覆盖、不合并。升级前先关闭旧游戏服务，防止旧进程继续向备份目录保存。迁移失败保留旧数据并可重试。路径由 `config/game.yaml` 的 `workspace.storage` 配置，`--workspace-store` 仍可显式指定其他目录：

```bash
python3 tools/tankbot.py serve --workspace-store /path/to/tankbot-project-store
python3 tools/tankbot.py browser --workspace /path/to/robot-seed --workspace-store /path/to/tankbot-project-store
```

`--workspace` 仅作为只读种子，不会回写玩家目录。模板更新和项目导入先展示旧模板/当前文件/新建议，默认保留已有文件；可按完整 revision 预览历史源码。重新启动使用启动示例，已保存草稿不会自动执行，须重新测试与部署。报告归档可导出，但不能绕过重新测试。

当前支持单模块兼容包装与多模块 Contract/Topic 图、同步周期/event 调度及 `tests/test_*.py` 的 unittest；多模块接口见 [M5 设计](docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)。测试还检查语法/合同/权限和 6 个授权传感器仿真批次，测试输出不控制当前世界。原生测试只适用于本人可信代码；浏览器测试在独立 Runtime origin 的 Worker 中进行。细节见 [M3 设计](docs/17_EDITOR_AND_DEPLOYMENT.md)。

## 玩家代码、依赖与运行日志

保存会保留整个文件；跨关卡只补缺失文件，已有算法、自建文件和框架均保留。系统框架升级先预览确认，旧版本可恢复。部署/重试清空的是 Python 运行内存，不是源码。

课程第三方库只开放 **NumPy**，另有指定基础标准库、SDK 和自建模块；不提供自由 pip 安装。游戏自行准备允许的库。静态检查和 Runtime 导入检查都会拒绝未开放的库，列表见 [课程策略](config/player-dependencies.yaml) 及游戏内说明。矩阵使用 ndarray；SDK 协方差为 `(3,3)` / `(2,2)` 只读数组，C2 当前测量可用 `tankbot.transforms.target_positions()` 转为 `(N,2)`。详见 [玩家代码与库](docs/23_PLAYER_CODE_AND_LIBRARIES.md)。

主界面右侧「日志」或代码编辑器内「运行日志」显示 `print()`、测试输出和异常调用栈。可筛选当前程序/测试/部署来源、清空显示，点击项目文件行号定位。日志标注版本；草稿已变化时提示行号差异。当前保留最近约 32 KiB，超量裁剪，不持续写入玩家存档。修复后重新测试/部署即可恢复程序，见 [运行日志设计](docs/24_RUNTIME_LOGS.md) 与 [验收](docs/reports/PLAYER_RUNTIME_VALIDATION.md)。

## 验证

独立测试工具使用已具备 `requirements.txt` 的解释器；可用开发虚拟环境，或 `.m1-cache/python/envs/*/ready.json` 记录的专用解释器。

```bash
python3 tools/check.py --offline    # Node自动发现 + Python + Rust + 文档 + 生成配置
npm test                           # 自动发现普通前端组件测试
python3 tools/check.py --suite python --offline
npm run test:wasm                   # 先构建原生debug及WASM release
npm run test:browser -- --mode both --offline  # C2工程实验流程，需已准备浏览器资源
npm run test:browser -- --scenario path-tracking --mode both --offline  # C3→C4真实编辑/通关
python3 docs/tools/check_design.py
python3 tools/export_profile.py --offline --check
python3 tools/build.py --format-check
```

单元/集成测试包含临时 loopback HTTP 服务；受限环境需允许本地套接字。`measure_m1.py` / `measure_m1b.py` 写入 current-profile 测量 JSON，保留原历史 baseline，报告实际机器/摘要/时延/误差；不要把本机测量当成所有平台性能保证。运行说明与边界见 [M1b 验证报告](docs/reports/M1B_VALIDATION.md)，旧 [M1 报告](docs/reports/M1_VALIDATION.md) 与基线保留为历史证据。

## 当前全向底盘

采用四个固定普通全向轮 X-drive，轮轴径向、滚动切向；轮心方位 45°/135°/225°/315°，R=0.25 m、轮半径 0.10 m。Core 编码器、Python 里程计和四组旋转安装的显示轮组共用 `wheels.omnidirectional` 标定，已替换旧平行麦轮。受力伺服/碰撞模型保持原约定。详见 [ADR-0019](docs/adr/0019-fourfold-omni-wheel-layout.md) 和 [验收](docs/reports/OMNI_VALIDATION.md)。

## 显示与相机

物理 60 Hz（4 子步）、视图快照 30 Hz、显示 requestAnimationFrame 独立运行；面板分别显示 SIM / VIEW / FPS。车体、炮台与授权弹丸按仿真时间缓存插值，断流不外推。相机跟随显示车体 x/y，世界 +x 向右、+y 向上，不跟随 yaw。没有合法估计时不显示全局车体，也不转为跟随真实位置。

显示时序在 `config/game.yaml` 的 rendering，默认练习缓存 80 ms、估计缓存 220 ms；底盘类型、几何、装甲/GPS 安装及部件外观在 `config/chassis/*.yaml`。差速保持 0.8×0.6 m，全向为 0.42×0.42 m、装甲中心 ±0.21 m；物理、教学与显示使用同一标定。应用配置版本现为 2.1、关卡 Schema 为 1.0，仍支持旧内联沙盒配置，启动不会覆盖自定义文件。设计见 [底盘模型](docs/29_CHASSIS_PROFILES.md) 与 [显示设计](docs/15_RENDERING_DESIGN.md)。

## 当前边界与设计入口

原生模式仅运行**本人可信的本机 Python**；普通子进程不是安全沙箱，不能开放第三方代码上传。UI 仅接收 View Policy 授权的估计/传感器或显式练习图层，不提供通用真值接口；本机设备所有者仍可通过文件/调试器读取自己的数据。实测为 Linux x86_64 原生和 Firefox 浏览器单机；Windows/macOS构建CI已配置，本次未取得其完整玩家流程证据，其他浏览器与服务器隔离仍待验证。

从 [文档索引](docs/README.md)、[物理确认记录](docs/13_PHYSICS_MODEL_DECISIONS.md) 与 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 阅读。根 [AGENTS.md](AGENTS.md) 已同步当前实现目录和检查入口；当前功能以本 README、文档索引及对应验收为准，历史报告按各自日期/平台范围保留。

M2 浏览器验收需先启动带 `--browser-qa` 的 browser 服务及启用 Marionette 的无头 Firefox，再运行 `python3 tools/browser_m2.py`；死循环用服务端 `--fault infinite_loop` 与工具 `--expect-fault`，程序武器用服务端 `--robot-demo` 与工具 `--expect-weapons`。普通构建/测试不需要下载 Pyodide；HTTP 资源边界测试在未准备 bundle 的 CI 中显式跳过，真实浏览器证据单独记录。

M3 UI 验收使用独立临时编辑库启动服务和 Marionette Firefox，再运行 `python3 tools/browser_m3.py`；原生模式使用 `--url http://127.0.0.1:8765 --output docs/reports/m3-native-ui.json`。脚本会修改该测试编辑库，勿指向日常项目。

弹窗/固定视口回归：启动本机服务与 Marionette Firefox 后运行 `python3 tools/browser_dialog.py`，检查 F2/按钮/×、草稿保留、焦点与按键隔离，以及不同窗口尺寸下编辑器铺满视口且无页面滚动。截图与测量写入 `.m1-cache/dialog-*.png` 和 `.m1-cache/dialog-report.json`。

## M5：Weapons 与多文件机器人

章节展示顺序保持 **Hello Robot（C0）、Weapons（C1–C5）、Navigation（C0–C5）**；公共 C0 后分为两条独立主线，展示顺序不产生解锁条件。C0–C2 玩法不变；C3 直接处理原始车体系距离/方位，输出仍是 `(r, theta)`，可实现 EKF；C4 沿用 C3 的中心 Radar 与差速敌车，玩家分文件实现中心预测与自动武器控制；C5 在此基础上加入匿名装甲观测、有效装甲与全向小陀螺，复用控制器并扩展旋转预测。Navigation 首关实现 FK/IK 与轮电压控制：系统发送 24 秒方形指令，按终点误差和真实路程验收，见 [设计与状态](docs/33_NAVIGATION_MOTION_CONTROL.md)。

C1–C5 底盘锁定并保留真实受力，系统自身位姿仍公开；C1–C3 人工炮台/开火，C4/C5 仅允许程序角加速度/单发。C3/C4/C5 时限为 120/120/180 仿真秒，首次成功部署起算。C2–C4 Radar 误差沿用 σr=0.45 m、σtheta=0.08 rad、10% 丢失；C4 不提供 GPS、不要求装甲命中，双方 HP、整车扣血和终局顺序与 C3 相同。C5 仅提供最近两块可见装甲的匿名车体系 `[r,theta]`，10 Hz、12 m，σr=0.03 m、σtheta=0.005 rad，每块独立丢失 10%，实际返回 0/1/2 行。没有中心 Radar 或 GPS，朝向按模 90° 解释。所有参数在对应 YAML。

F2 的 tree 风格文件树高亮本关主要编辑文件；C4 高亮 `perception/polar_tracker.py`、`weapons/target_prediction.py`、`weapons/auto_aim.py`。C5 高亮 `perception/armor_tracker.py`、`weapons/target_prediction.py` 与 `weapons/auto_aim.py`，分别处理匿名关联/估计、预测和炮台控制。自己选择滤波、预测及 PD 等控制方法；接口与对称性说明见 [匿名装甲设计](docs/30_ARMOR_OBSERVATIONS.md)。新脚手架需更新时先预览；已有算法（包括旧 `auto_aim.py`）不会被自动覆盖。旧关卡 ID 和已完成进度保留，C5 依赖 C4。

C3/C4 的 `PolarTracker.update` 接收 `measurements: tuple[PolarTargetEstimate, ...]`，用 `.range_m` / `.bearing_rad` 读取，缺测为 `()`；自身位姿与算法内部矩阵仍用 NumPy。两关脚手架现为 5.0.0，旧数组接口的算法文件会保留，需自行按新签名适配后重新测试；完整示例见 [28](docs/28_WEAPONS_PROGRESSIVE_ESTIMATION.md)。

默认教学项目跨 C0–C5 共用稳定工作区，与启动关卡、控制模式和模板版本无关。旧版本分库中的已编辑项目会完整复制到新默认目录，原源码和全部历史保留；多份已编辑库不自动合并，需用 `--workspace-store PATH` 明确选择。升级后重启服务，详见 [工作区存储](docs/17_EDITOR_AND_DEPLOYMENT.md)。

开发者可用 `python3 tools/tankbot.py serve --developer --level c5`，或 `browser --developer --level c5` 直达练习；正式玩家按存档解锁。接口、物理与兼容见 [新课程设计](docs/28_WEAPONS_PROGRESSIVE_ESTIMATION.md)，模块调度见 [26](docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)，当前证据见 [验收](docs/reports/WEAPONS_REDESIGN_VALIDATION.md)。

## YAML 关卡插件

当前十二关通过同一加载器自动发现，稳定 ID、存档及既有 Topic 保持兼容；早期五关迁移与后续 Weapons 调整的历史分别保留于对应报告。复用已有组件时，只需在 `levels/` 添加一个符合 Schema 的 YAML，无需修改引擎、UI 或注册列表；程序输入权限与 UI 显示权限独立配置。启动器会为原生和浏览器生成同一关卡目录，新增文件后重启服务。未知组件会明确拒绝，不支持 YAML 执行脚本。

编写及启动流程见 [关卡指南](levels/README.md)，架构与原五关审计见 [27](docs/27_LEVEL_PLUGIN_ARCHITECTURE.md)，测试与限制见 [迁移验收](docs/reports/LEVEL_PLUGINS_VALIDATION.md)。

## 双主线与 Navigation 首关

当前进度树为 `c0 → {Weapons: c1→c2→c3→c4→c5, Navigation: navigation.c0→navigation.c1→navigation.c2→navigation.c3→navigation.c4}`。关卡路线显示已通关、可挑战、锁定和当前节点，锁定节点可查看具体缺少的前置。存档保持版本1，允许非连续完成集合；两个独立工作区的源码和历史保留。设计见 [双主线进度](docs/36_BRANCHING_PROGRESSION.md)。

通关公共 c0 后即开放 Navigation C0（稳定 ID navigation.c0），不要求先完成 Weapons C5：

```bash
python3 tools/tankbot.py serve --level navigation.c0
```

开发者预览可追加 --developer；浏览器模式用 browser 替换 serve。F2 只需修改高亮的 control/wheel_controller.py，输入目标 Twist、左右轮速与 dt，返回左右轮电压 NumPy 向量。模型参数在 config/chassis/differential.yaml；指令与验收在 levels/navigation.C0.yaml。Navigation 使用独立工程，Weapons 源码/历史继续保留；本章没有武器或人工驾驶。

Navigation C0/C1 可在右侧“曲线”中对比参考与编码器速度、两轮角速度及执行电压；点击“放大曲线”可四图同屏查看，结束后曲线保留。C1 复用你的轮控制器，只新增 localization/odometry.py，使用理想轮速推算自己的位姿，运行中显示位置/朝向 RMSE。

```bash
python3 tools/tankbot.py serve --level navigation.c1 --developer
```

玩家模式需先通关 Navigation C0。已有工程切关时如提示系统脚手架升级，可在 F2 中预览并更新模块连接；轮控制器源码完整保留。接口与验收见 [Navigation 里程计设计](docs/34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md)。

Navigation C2 在通关 C1 后解锁，复用已有控制器/里程计，只新增 localization/ekf.py，填写 predict 与 correct，维护 NumPy state (3,) 和 covariance (3,3)。GPS 提供2 Hz带噪地图系位置，编码器增加固定增益误差和速率噪声；三个算法共享同一测量。F2 指南提供完整类型、单位、Jacobian 和更新公式。

```bash
python3 tools/tankbot.py serve --level navigation.c2 --developer
```

默认车体/相机跟随 EKF；图层可单独显示带噪 GPS、纯里程计轨迹与1σ位置椭圆，运行中比较两组 RMSE。24秒末按实际路程≥7.2 m、EKF位置RMSE≤0.15 m、朝向RMSE≤0.15 rad、有效估计≥100次通关，不再要求真实终点回原点。切换显示来源不改评分，真值仅在独立开发者图层显示；已有算法与历史保留。设计及本机验收见 [GPS/EKF](docs/35_NAVIGATION_GPS_LOCALIZATION.md)。

Navigation C3 在通关 C2 后解锁，复用轮控制器、里程计和 EKF，只新增 `navigation/waypoint_controller.py`：输入地图系估计 `[x,y,yaw]`、当前航点 `[x,y]` 和 `dt`，返回 `Twist` 速度参考，再由已有轮控制器执行。地图显示可切换的公开路线、航点编号和目标容差圈。

```bash
python3 tools/tankbot.py serve --level navigation.c3
# 开发者预览
python3 tools/tankbot.py browser --level navigation.c3 --developer
```

120 仿真秒内按顺序进入四个航点的 0.35 m 范围，最后在终点满足平移速率≤0.05 m/s、绝对角速度≤0.10 rad/s 连续0.5秒通关。首次正式轮控制生效起算；位置控制参考限幅 vx ±0.5 m/s、wz ±1.5 rad/s，缺少有效定位时制动。定位 RMSE 继续用于反馈，不额外设为通关门槛。路线、时限、容差、停稳与显示参数均在 [关卡 YAML](levels/navigation.C3.yaml)，详细接口和时序见 [航点闭环](docs/37_NAVIGATION_WAYPOINT_CONTROL.md)。已有算法/历史保留；系统文件升级先预览，测试与正式任务隔离。


## 工程工具与算法实验台

任务页的“算法实验台”目前由 Weapons C2 显式开放：部署后开始/停止录制，结束尝试，再选择两个保存版本比较同一组授权输入。可查看实际执行、测量/估计/协方差、累计和分段误差、缺测、可选创新及原生Python错误栈，保存/导出失败复现记录。导出含源码、revision、配置/环境摘要和时刻，不含敌车真值；重新导入没有私有参考时，新RMSE留空。传感器回放不是完整通关，控制器须从同初态重跑，不能套用旧测量。

“日志→耗时诊断”显示整批/模块、编解码、往返及收到至提交的合并耗时，提供p50/p95/p99/p99.9/max与失败位置，并显示冻结profile。声明总上限与后端墙钟已分开，见下节；固定tick/6tick门不变，遥测不是CPU配额。F2“模板、备份与恢复→项目容量与完整备份”可导出整个当前课程工程、固定历史版本，预览并确认可恢复清理；旧源码/历史不自动删除。恢复前备份当前HEAD，异常中断可以回滚。工程配额在 [engineering.yaml](config/engineering.yaml)。

完整接口、操作及限制见 [工程与实验台](docs/38_ENGINEERING_AND_ALGORITHM_LAB.md)，实际命令/截图/失败见 [本轮验收](docs/reports/ENGINEERING_QUALITY_VALIDATION_20261105.md)，当前风险见 [评估跟进](docs/reports/PROJECT_REVIEW_FOLLOWUP_20261105.md)。连续路径追踪已作为Navigation C4实施，见 [设计与验收](docs/40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)。已知地图规划已按用户确认实现为 [Navigation C5](docs/42_NAVIGATION_GLOBAL_PLANNING.md)。局部避障及IMU/建图/SLAM仍为 [课程提案](docs/39_NAVIGATION_COURSE_PROPOSALS.md)。CI跨平台构建与Linux/Firefox实际玩家流程分别记录；其他OS/浏览器仍需独立实测。

## Runtime 执行 profile 与可重复基准

[config/runtime-profiles.yaml](config/runtime-profiles.yaml) 独立定义模块声明总上限和原生/Pyodide整批墙钟截止。当前实验性默认为声明总上限20ms、原生整批30ms、Pyodide整批40ms。可信后端在一次尝试开始前冻结profile，测试、部署与回放继承；日志中的ID、版本、参数和摘要可追踪。旧`runtime.batch_budget_ms`仅在不含新profile时保持原来的双重语义，混用报错。固定6tick提交不随墙钟时限移动，模块耗时自报不构成CPU配额。

```bash
python3 tools/benchmark_runtime.py --plan --offline
python3 tools/benchmark_runtime.py --backend native --workloads weapons_kf --output .m1-cache/my-native-budget --offline
# 先完成WASM构建及prepare_browser；使用独立Firefox目录/端口，不访问日常userdata
python3 tools/benchmark_runtime.py --backend pyodide --workloads navigation_path --output .m1-cache/my-browser-budget --offline
python3 tools/calibrate_runtime_benchmark.py --backend native --output .m1-cache/my-budget-calibration --offline
```

基准参数来自 [config/runtime-benchmark.yaml](config/runtime-benchmark.yaml)。near_cap负载需先校准并通过`--calibration-file`传入冻结结果。逐批事件写入有界JSONL分片，`summary.json`保留首次激活/稳态、阶段分位数、截断和完整实验结果。`--slice-attempts --batches-per-cell 12`只验证工具链；不代表完整关卡或可靠性验收。传感器回放不能替代真实闭环对照。命令、当前证据范围及默认选择依据见 [41](docs/41_RUNTIME_EXECUTION_PROFILES.md)。

## Navigation C5：已知地图全局规划

通过Navigation C4后解锁C5。F2主要编辑`navigation/global_planner.py`，输入为原始只读`OccupancyGrid`、公开起终点和安全参数；自行完成4格方形膨胀、搜索及路径后处理，允许A*、Dijkstra等不同方法。框架只做坐标转换与独立路径校验，不提供搜索解。测试与正式部署各用新Runtime完整规划一次，原生/Pyodide均独立5秒墙钟；正式校验后从首次轮电压生效起计120仿真秒，无碰撞到点并停稳即可，不沿用C4检查点或追踪RMSE门槛。周期20ms声明/30或40ms实验性墙钟及6tick不变。已有四项算法、源码与历史保留，Manifest升级先预览。地图/安全膨胀/合法路径可独立显示，完整合同见 [42](docs/42_NAVIGATION_GLOBAL_PLANNING.md)、实测与截图见 [验收报告](docs/reports/NAVIGATION_GLOBAL_PLANNING_VALIDATION.md)。

```bash
python3 tools/tankbot.py serve --level navigation.c5
python3 tools/tankbot.py browser --level navigation.c5
python3 tools/check.py --suite browser --offline -- --scenario global-planning --seed 0 --planner astar
```

前两条沿用玩家存档前置检查；开发者模式按既有设置自由练习。第三条创建隔离设置、存档、工程、端口与Firefox目录，使用测试专用参考源码，未执行前不能据此宣称平台流程通过。
