# TankBot

TankBot 将二维坦克运动、机器人算法学习与多文件 Python 编程结合。玩家通过传感器和自己的算法重建世界认知。

当前完成 **M1 + M1b 本机闭环原型**：Rust/Rapier2D 权威物理、差速/四轮径向全向轮底盘、理想轮编码器与质心 IMU、外部 Python 里程计、固定 tick 提交、Pose Selector、View Policy 和 Canvas 页面。M1b 增加双刚体炮台、单发/冷却、连续弹道/反弹/弹丸互毁、后坐/受击冲量、靶标与 Python 武器接口；M2 增加真实浏览器 Rust/WASM + Pyodide 双 Worker、独立 Runtime origin 与多 Adapter 验证；M3 增加 CodeMirror/Vim、多文件 Workspace、模板预览、快照测试、部署与回滚。M5 增加模块图，现已调整为 C3 极坐标滤波、C4 中心自瞄与 C5 小陀螺装甲；Locomotion、规划和 Arena 尚未实现。

M4 增加 C0–C2 教学关卡：真值驾驶练习、理想雷达 SE(3) 矩阵变换、带噪声/丢失的移动敌车跟踪与击杀。开始方式见下节；M5 当前课程为 C3 直接滤波车体系 (r, theta)、C4 复用滤波并接管武器自瞄、C5 全向小陀螺装甲预测；自身定位课程、建图、规划与 Arena 仍待实现。

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

在「任务」面板选择 C0/C1/C2，点击「开始 / 重试」。C0 先移动至少 1 m、转动车体至少 0.5 rad，并命中可见靶标。C1 隐藏敌车，F2 打开编辑器，完成自动生成的 `perception/transforms.py`，返回 `NDArray[np.float64]` 形式的 4×4 SE(3) 矩阵，测试并部署，利用目标估计瞄准命中。C2 保留该矩阵函数，追加 `perception/tracker.py`；处理带噪声和 10% 丢失的雷达，跟踪巡逻敌车，保持存活并击中三次使敌车 HP 归零即可通关。

前三关保留系统自定位、公开地图与手动控制。Radar 是车体系局部观测，地图上的目标标记来自玩家 Python；Weapons C1–C5 默认显示炮弹，可在图层设置中开关；真实敌车和命中特效位置仍隐藏，Python 输入权限不变。C2 显示双方 HP，以及运行中的累计位置 RMSE、有效样本数和变化曲线；编辑器也显示同一指标。测试不计入、重复部署不清零，重试重新累计。通关或点击「结束本次尝试」后关闭玩家程序并冻结最终误差报告；物理与已有弹丸继续运行。重试建立新场景，新关只补缺失文件，已有源码保留；保存的草稿须重新 Test/Deploy。玩家按 C0 → C1 → C2 解锁，通关写入存档；开发者模式可自由选关练习。

F1 或编辑器中的「关卡说明 / 类型」可随时查看每关步骤、输入输出签名、SDK 字段/单位、Python 速查与交互矩阵实验；悬停及 Ctrl+Space 提供类型提示。新模板显式标注变量和返回类型。旧工作区可预览模板升级并选择系统脚手架，已有算法默认保留。原生 NumPy 随首次启动自动准备；浏览器运行 `prepare_browser.py` 准备锁定的 Pyodide/NumPy 资源。

旧工作区点击「测试快照」时，若运行框架仍为旧版，会先打开更新预览；确认「保留算法，更新框架并继续测试」后继续。已有算法文件排除在替换计划之外，旧运行文件可从历史版本恢复。测试检查语法/导入/接口、项目单元测试和默认 6 批授权传感器试运行；C1 包含 SE(3) 样例，不要求先通关。当前快照通过测试后部署按钮才会亮；旁边会说明等待、失败或重新测试的原因。

C0/C1/C2 分别限时 **60/60/120 仿真秒**。C0 首次有效人工操作起算；C1/C2 首次成功部署玩家程序起算，之前的编辑和测试不计时。正式运行期间锁定代码编辑器，须先点击任务页的「结束本次尝试」，或「开始 / 重试」重置关卡，再修改代码；倒计时不因算法错误暂停。C2 玩家与敌车同为 3 HP，反弹自伤也扣血，玩家死亡或超时判失败。详见 [关卡规则与参数](docs/25_ATTEMPT_RULES_AND_CONFIGURATION.md)。

完整模型和接口见 [M4 设计](docs/18_CAMPAIGN_DESIGN.md) 与 [学习说明设计](docs/19_LEARNING_GUIDES_AND_SE3.md)，验证见 [M4 报告](docs/reports/M4_VALIDATION.md) 及 [SE(3) 学习工具验收](docs/reports/LEARNING_VALIDATION.md)。

默认炮台 J/L 转动，空格或按钮单发（长按不连射）。开发者自由试验场的估计视图隐藏真实弹丸，保留炮台与武器局部反馈；`--developer --view weapons-practice` 明确授权练习图层。Python 输入权限不增加。`--robot-demo` 使用独立的 [weapon_demo.py](examples/robot/weapon_demo.py) 控制炮台/开火，人工底盘仍可用；对应人工武器入口会拒绝。想观察程序控制可运行 `python3 tools/tankbot.py serve --developer --robot-demo --view weapons-practice`。

通用物理模型、控制器数值及平台参数在 [config/game.yaml](config/game.yaml)；六关的地图组合、传感器、权限、规则、合同和教材分别在 [levels/](levels/README.md) 的独立 YAML 中，缺项报错，不补隐藏默认值。底盘只能在场景启动时选择。可在网页中保存、测试并部署 Python 项目；编辑与部署分离，成功部署不重置物理世界。示例算法在 [examples/robot](examples/robot/localization/odometry.py)，支持多文件 import，启动不会改写源码。

## 设置、玩家存档与开发者图层

点击顶部「设置」或默认 **F10** 打开设置页面，× 关闭。可修改键盘绑定、恢复默认键位，并切换开发者模式；编辑器默认 F2、说明默认 F1，也可改键。设置界面打开期间暂停驾驶与开火。模式切换会重新开始关卡，先保存代码并等待测试/部署结束。

首次创建 `userdata/settings.yaml`，保存键盘映射、开发者开关和图层选择；默认模板在 [config/settings.yaml](config/settings.yaml)。玩家通关记录在 `userdata/progress.json`，刷新或重启后保留；首次只开放 C0，完成后解锁下一关，CLI/API 同样检查存档。可以用 `--settings-file /path/settings.yaml --save-file /path/progress.json` 指定自己的文件。损坏或未知版本的文件报错并保留原件。

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

打开 `http://127.0.0.1:8765/?runtime=browser`，操作与原生模式相同。首次启动会加载两个 Python 解释器；Test/Deploy 时额外启动候选 Worker，当前机器人继续运行。玩家源码在页面中编辑并显式部署；修改 SDK/Authority 源码须重新 prepare bundle 并刷新。`--view weapons-practice` / `--robot-demo` 同样适用。资源准备后可运行 `python3 tools/prepare_browser.py --offline`；底盘/武器参数仍只在 config/game.yaml。两个 loopback 端口默认 8765/8766，不能与原生服务同时占用同一端口。

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
cargo test --locked
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs  # Node 22+，浏览器表现行为测试
node tests/test_sdk_hints.mjs  # 学习类型与成员提示
node tests/test_gamepad.mjs    # 模拟量、按键、设备切换和恢复边界
node tests/test_settings.mjs   # 改键语义、图层权限和真值/估计独立
node tests/test_runtime_logs.mjs # 连续 Python 日志、版本隔离和源码行号
node tests/test_live_metrics.mjs # 累计指标展示、曲线容量和重试清零
node tests/test_wasm.mjs       # 先构建原生 debug 与 WASM release
python3 docs/tools/check_design.py
python3 tools/build.py --format-check
python3 tools/build.py --wasm
node tools/wasm_probe.mjs
python3 tools/measure_omni.py
```

单元/集成测试包含临时 loopback HTTP 服务；受限环境需允许本地套接字。`measure_m1.py` / `measure_m1b.py` 写入 current-profile 测量 JSON，保留原历史 baseline，报告实际机器/摘要/时延/误差；不要把本机测量当成所有平台性能保证。运行说明与边界见 [M1b 验证报告](docs/reports/M1B_VALIDATION.md)，旧 [M1 报告](docs/reports/M1_VALIDATION.md) 与基线保留为历史证据。

## 当前全向底盘

采用四个固定普通全向轮 X-drive，轮轴径向、滚动切向；轮心方位 45°/135°/225°/315°，R=0.25 m、轮半径 0.10 m。Core 编码器、Python 里程计和四组旋转安装的显示轮组共用 `wheels.omnidirectional` 标定，已替换旧平行麦轮。受力伺服/碰撞模型保持原约定。详见 [ADR-0019](docs/adr/0019-fourfold-omni-wheel-layout.md) 和 [验收](docs/reports/OMNI_VALIDATION.md)。

## 显示与相机

物理 60 Hz（4 子步）、视图快照 30 Hz、显示 requestAnimationFrame 独立运行；面板分别显示 SIM / VIEW / FPS。车体、炮台与授权弹丸按仿真时间缓存插值，断流不外推。相机跟随显示车体 x/y，世界 +x 向右、+y 向上，不跟随 yaw。没有合法估计时不显示全局车体，也不转为跟随真实位置。

显示时序在 `config/game.yaml` 的 rendering，默认练习缓存 80 ms、估计缓存 220 ms；底盘类型、几何、装甲/GPS 安装及部件外观在 `config/chassis/*.yaml`。差速保持 0.8×0.6 m，全向为 0.42×0.42 m、装甲中心 ±0.21 m；物理、教学与显示使用同一标定。应用配置版本现为 2.0、关卡 Schema 为 1.0，仍支持旧内联沙盒配置，启动不会覆盖自定义文件。设计见 [底盘模型](docs/29_CHASSIS_PROFILES.md) 与 [显示设计](docs/15_RENDERING_DESIGN.md)。

## 当前边界与设计入口

原生模式仅运行**本人可信的本机 Python**；普通子进程不是安全沙箱，不能开放第三方代码上传。UI 仅接收 View Policy 授权的估计/传感器或显式练习图层，不提供通用真值接口；本机设备所有者仍可通过文件/调试器读取自己的数据。实测为 Linux x86_64 原生和 Firefox 浏览器单机；Windows/macOS 构建 CI 已配置但尚无本次运行证据，其他浏览器与服务器隔离仍待验证。

从 [文档索引](docs/README.md)、[物理确认记录](docs/13_PHYSICS_MODEL_DECISIONS.md) 与 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 阅读。根 [AGENTS.md](AGENTS.md) 按用户要求保留原文件；其中“只有设计文档”的状态描述为历史基线，当前实现范围以本 README、[M1 收尾](docs/reports/M1_CLOSEOUT.md) 、[M2 报告](docs/reports/M2_VALIDATION.md) 、[M3 报告](docs/reports/M3_VALIDATION.md) 和 [M4 报告](docs/reports/M4_VALIDATION.md) 为准，其架构约束继续有效。

M2 浏览器验收需先启动带 `--browser-qa` 的 browser 服务及启用 Marionette 的无头 Firefox，再运行 `python3 tools/browser_m2.py`；死循环用服务端 `--fault infinite_loop` 与工具 `--expect-fault`，程序武器用服务端 `--robot-demo` 与工具 `--expect-weapons`。普通构建/测试不需要下载 Pyodide；HTTP 资源边界测试在未准备 bundle 的 CI 中显式跳过，真实浏览器证据单独记录。

M3 UI 验收使用独立临时编辑库启动服务和 Marionette Firefox，再运行 `python3 tools/browser_m3.py`；原生模式使用 `--url http://127.0.0.1:8765 --output docs/reports/m3-native-ui.json`。脚本会修改该测试编辑库，勿指向日常项目。

弹窗/固定视口回归：启动本机服务与 Marionette Firefox 后运行 `python3 tools/browser_dialog.py`，检查 F2/按钮/×、草稿保留、焦点与按键隔离，以及不同窗口尺寸下编辑器铺满视口且无页面滚动。截图与测量写入 `.m1-cache/dialog-*.png` 和 `.m1-cache/dialog-report.json`。

## M5：Weapons 与多文件机器人

章节按 **Hello Robot（C0）→ Weapons（C1–C5）→ 后续 Locomotion** 排列。C0–C2 玩法不变；C3 直接处理原始车体系距离/方位，输出仍是 `(r, theta)`，可实现 EKF；C4 沿用 C3 的中心 Radar 与差速敌车，玩家分文件实现中心预测与自动武器控制；C5 在此基础上加入匿名装甲观测、有效装甲与全向小陀螺，复用控制器并扩展旋转预测。

C1–C5 底盘锁定并保留真实受力，系统自身位姿仍公开；C1–C3 人工炮台/开火，C4/C5 仅允许程序角加速度/单发。C3/C4/C5 时限为 120/120/180 仿真秒，首次成功部署起算。C2–C4 Radar 误差沿用 σr=0.45 m、σtheta=0.08 rad、10% 丢失；C4 不提供 GPS、不要求装甲命中，双方 HP、整车扣血和终局顺序与 C3 相同。C5 仅提供最近两块可见装甲的匿名车体系 `[r,theta]`，10 Hz、12 m，σr=0.03 m、σtheta=0.005 rad，每块独立丢失 10%，实际返回 0/1/2 行。没有中心 Radar 或 GPS，朝向按模 90° 解释。所有参数在对应 YAML。

F2 的 tree 风格文件树高亮本关主要编辑文件；C4 高亮 `perception/polar_tracker.py`、`weapons/target_prediction.py`、`weapons/auto_aim.py`。C5 高亮 `perception/armor_tracker.py`、`weapons/target_prediction.py` 与 `weapons/auto_aim.py`，分别处理匿名关联/估计、预测和炮台控制。自己选择滤波、预测及 PD 等控制方法；接口与对称性说明见 [匿名装甲设计](docs/30_ARMOR_OBSERVATIONS.md)。新脚手架需更新时先预览；已有算法（包括旧 `auto_aim.py`）不会被自动覆盖。旧关卡 ID 和已完成进度保留，C5 依赖 C4。

开发者可用 `python3 tools/tankbot.py serve --developer --level c5`，或 `browser --developer --level c5` 直达练习；正式玩家按存档解锁。接口、物理与兼容见 [新课程设计](docs/28_WEAPONS_PROGRESSIVE_ESTIMATION.md)，模块调度见 [26](docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)，当前证据见 [验收](docs/reports/WEAPONS_REDESIGN_VALIDATION.md)。

## YAML 关卡插件

当前 C0–C5 通过同一加载器自动发现，旧 ID、存档及既有 Topic 保持兼容；C3/C4 按用户要求重做，C5 为本轮新增。复用已有组件时，只需在 `levels/` 添加一个符合 Schema 的 YAML，无需修改引擎、UI 或注册列表；程序输入权限与 UI 显示权限独立配置。启动器会为原生和浏览器生成同一关卡目录，新增文件后重启服务。未知组件会明确拒绝，不支持 YAML 执行脚本。

编写及启动流程见 [关卡指南](levels/README.md)，架构与原五关审计见 [27](docs/27_LEVEL_PLUGIN_ARCHITECTURE.md)，测试与限制见 [迁移验收](docs/reports/LEVEL_PLUGINS_VALIDATION.md)。
