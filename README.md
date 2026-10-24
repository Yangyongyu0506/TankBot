# TankBot

TankBot 将二维坦克运动、机器人算法学习与多文件 Python 编程结合。玩家通过传感器和自己的算法重建世界认知。

当前完成 **M1 + M1b 本机闭环原型**：Rust/Rapier2D 权威物理、差速/四轮径向全向轮底盘、理想轮编码器与质心 IMU、外部 Python 里程计、固定 tick 提交、Pose Selector、View Policy 和 Canvas 页面。M1b 增加双刚体炮台、单发/冷却、连续弹道/反弹/弹丸互毁、后坐/受击冲量、靶标与 Python 武器接口；M2 增加真实浏览器 Rust/WASM + Pyodide 双 Worker、独立 Runtime origin 与多 Adapter 验证；M3 增加 CodeMirror/Vim、多文件 Workspace、模板预览、快照测试、部署与回滚。后续课程与 Arena 尚未实现。

M4 增加 C0–C2 教学关卡：真值驾驶练习、理想雷达 SE(3) 矩阵变换、带噪声/丢失的移动敌车跟踪与击杀。开始方式见下节；完整后续课程、自动规划和 Arena 仍待实现。

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

在「任务」面板选择 C0/C1/C2，点击「开始 / 重试」。C0 先移动至少 1 m、转动车体至少 0.5 rad，并命中可见靶标。C1 隐藏敌车，F2 打开编辑器，完成自动生成的 `perception/transforms.py`，返回 `NDArray[np.float64]` 形式的 4×4 SE(3) 矩阵，测试并部署，利用目标估计瞄准命中。C2 保留该矩阵函数，追加 `perception/tracker.py`；处理带噪声和 10% 丢失的雷达，跟踪巡逻敌车，击中三次使其 HP 归零即可通关。

前三关保留系统自定位、公开地图与手动控制。Radar 是车体系局部观测，地图上的目标标记来自玩家 Python；玩家 C1/C2 不显示真实敌车、真实弹道或命中特效位置。C2 显示授权 HP。通关或点击「结束并评估」后关闭玩家程序，再显示估计误差；物理与已有弹丸继续运行。重试建立新场景，新关只补缺失文件，已有源码保留；保存的草稿须重新 Test/Deploy。玩家按 C0 → C1 → C2 解锁，通关写入存档；开发者模式可自由选关练习。

F1 或编辑器中的「关卡说明 / 类型」可随时查看每关步骤、输入输出签名、SDK 字段/单位、Python 速查与交互矩阵实验；悬停及 Ctrl+Space 提供类型提示。新模板显式标注变量和返回类型。旧工作区可预览模板升级并选择系统脚手架，已有算法默认保留。原生 NumPy 随首次启动自动准备；浏览器运行 `prepare_browser.py` 准备锁定的 Pyodide/NumPy 资源。

旧工作区点击「测试快照」时，若运行框架仍为旧版，会先打开更新预览；确认「保留算法，更新框架并继续测试」后继续。已有算法文件排除在替换计划之外，旧运行文件可从历史版本恢复。测试检查语法/导入/接口、项目单元测试和默认 6 批授权传感器试运行；C1 包含 SE(3) 样例，不要求先通关。当前快照通过测试后部署按钮才会亮；旁边会说明等待、失败或重新测试的原因。

完整模型和接口见 [M4 设计](docs/18_CAMPAIGN_DESIGN.md) 与 [学习说明设计](docs/19_LEARNING_GUIDES_AND_SE3.md)，验证见 [M4 报告](docs/reports/M4_VALIDATION.md) 及 [SE(3) 学习工具验收](docs/reports/LEARNING_VALIDATION.md)。

默认炮台 J/L 转动，空格或按钮单发（长按不连射）。开发者自由试验场的估计视图隐藏真实弹丸，保留炮台与武器局部反馈；`--developer --view weapons-practice` 明确授权练习图层。Python 输入权限不增加。`--robot-demo` 使用独立的 [weapon_demo.py](examples/robot/weapon_demo.py) 控制炮台/开火，人工底盘仍可用；对应人工武器入口会拒绝。想观察程序控制可运行 `python3 tools/tankbot.py serve --developer --robot-demo --view weapons-practice`。

所有物理模型、控制器数值、场景及运行 profile 集中在 [config/m1.json](config/m1.json)，缺项报错，不补隐藏默认值。底盘只能在场景启动时选择。可在网页中保存、测试并部署 Python 项目；编辑与部署分离，成功部署不重置物理世界。示例算法在 [examples/robot](examples/robot/localization/odometry.py)，支持多文件 import，启动不会改写源码。

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

摇杆控制目标速度比例，松开后主动制动。键盘按住时按执行器优先；编辑、切出页面或断连会清除手柄目标，返回后需先回中。程序接管的执行器不接受人工指令。映射、方向、死区和速度均在 `config/m1.json` 的 `view.gamepad`；非标准手柄可显式配置索引。远程网页需 HTTPS，本机 localhost 可用。设计及硬件验证边界见 [手柄设计](docs/20_GAMEPAD_INPUT.md) 与 [验收报告](docs/reports/GAMEPAD_VALIDATION.md)。

`tools/build.py` 构建 Rust Core，并自动检查 `package-lock.json` 和已安装的 npm 依赖：缺失或版本不匹配时执行锁定安装，然后每次重新构建编辑器及许可证文件。`--web-only` 只修复/构建编辑器，`--core-only` 用于无需 Node.js 的无头核心构建；`--offline` 要求 Cargo 与 npm 依赖已在本机缓存。缺少 Node.js/npm 时会报出安装要求，不会假装 UI 已构建。脚本优先使用正常 Cargo；未安装时可使用本机已有的 `.tools/rust` 工具链与 `.tools/cargo` 缓存。这些目录被忽略，不是分发依赖。常规 Rust 环境也可直接 `cargo build --locked`，但它不生成编辑器资源。

## 浏览器单机（M2 本机验收）

同一 Rust Core 与 Python SDK/Authority 在浏览器两个 Worker 内运行；启动器提供静态资源、只读启动种子与版本化 Workspace 存储，不在服务端执行玩家 Python 或仿真。

```bash
python3 tools/build.py --wasm --release
python3 tools/prepare_browser.py          # 首次下载锁定版本/摘要的 Pyodide
python3 tools/tankbot.py browser --chassis omnidirectional
```

打开 `http://127.0.0.1:8765/?runtime=browser`，操作与原生模式相同。首次启动会加载两个 Python 解释器；Test/Deploy 时额外启动候选 Worker，当前机器人继续运行。玩家源码在页面中编辑并显式部署；修改 SDK/Authority 源码须重新 prepare bundle 并刷新。`--view weapons-practice` / `--robot-demo` 同样适用。资源准备后可运行 `python3 tools/prepare_browser.py --offline`；底盘/武器参数仍只在 config/m1.json。两个 loopback 端口默认 8765/8766，不能与原生服务同时占用同一端口。

已验证 Linux / Firefox 157，其他平台仍待验证。Runtime origin 的 CSP 限制跨 origin 网络/嵌套 Worker，仍没有浏览器硬内存/CPU/存储额度。服务器沙箱、Arena 与第三方代码上传未开放。详细流程及代价见 [浏览器设计](docs/16_BROWSER_RUNTIME.md)。

## 多文件编辑与部署（M3）

游戏界面固定在视口内，无需滚动网页。点击顶部「代码编辑器」或按默认 **F2** 弹出 Workspace；再次按对应快捷键 或点击右上角 **×** 收起。草稿、光标与选中文件会保留。Workspace 支持 Python/JSON 编辑、Vim、文件切换、新建文件、Ctrl/⌘S 或 `:w` 保存。依次点击 **测试快照 → 部署已测试版本**；测试或候选启动失败会保留当前机器人。历史部署可显式回滚，产生新 Runtime 并清空算法状态，物理世界继续运行。编辑器焦点不会把 W/J/L/空格传给坦克。

默认编辑库保存在 `.m1-cache/workspaces/`，源码、模板 ledger 和测试/部署归档跨刷新保留。建议长期项目指定自己的持久目录，并定期导出备份：

```bash
python3 tools/tankbot.py serve --workspace-store /path/to/tankbot-project-store
python3 tools/tankbot.py browser --workspace /path/to/robot-seed --workspace-store /path/to/tankbot-project-store
```

`--workspace` 仅作为只读种子，不会回写玩家目录。模板更新和项目导入先展示旧模板/当前文件/新建议，默认保留已有文件；可按完整 revision 预览历史源码。重新启动使用启动示例，已保存草稿不会自动执行，须重新测试与部署。报告归档可导出，但不能绕过重新测试。

当前支持一个周期 Module 及其多文件依赖、`tests/test_*.py` 的 unittest；完整多模块图属于 M5。测试还检查语法/合同/权限和 6 个授权传感器仿真批次，测试输出不控制当前世界。原生测试只适用于本人可信代码；浏览器测试在独立 Runtime origin 的 Worker 中进行。细节见 [M3 设计](docs/17_EDITOR_AND_DEPLOYMENT.md)。

## 验证

独立测试工具使用已具备 `requirements.txt` 的解释器；可用开发虚拟环境，或 `.m1-cache/python/envs/*/ready.json` 记录的专用解释器。

```bash
cargo test --locked
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs  # Node 22+，浏览器表现行为测试
node tests/test_sdk_hints.mjs  # 学习类型与成员提示
node tests/test_gamepad.mjs    # 模拟量、按键、设备切换和恢复边界
node tests/test_settings.mjs   # 改键语义、图层权限和真值/估计独立
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

显示参数在 `config/m1.json` 的 rendering，默认练习缓存 80 ms、估计缓存 220 ms；差速 tracked 与全向 radial_omni 使用独立部件/颜色配置。配置内部版本现为 1.6，新增 campaign 段；仍支持 1.5 沙盒配置，使用教学关卡须显式添加新配置，启动不会自动覆盖。设计与浏览器证据见 [显示设计](docs/15_RENDERING_DESIGN.md) 和 [验收报告](docs/reports/RENDERING_VALIDATION.md)。

## 当前边界与设计入口

原生模式仅运行**本人可信的本机 Python**；普通子进程不是安全沙箱，不能开放第三方代码上传。UI 仅接收 View Policy 授权的估计/传感器或显式练习图层，不提供通用真值接口；本机设备所有者仍可通过文件/调试器读取自己的数据。实测为 Linux x86_64 原生和 Firefox 浏览器单机；Windows/macOS 构建 CI 已配置但尚无本次运行证据，其他浏览器与服务器隔离仍待验证。

从 [文档索引](docs/README.md)、[物理确认记录](docs/13_PHYSICS_MODEL_DECISIONS.md) 与 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 阅读。根 [AGENTS.md](AGENTS.md) 按用户要求保留原文件；其中“只有设计文档”的状态描述为历史基线，当前实现范围以本 README、[M1 收尾](docs/reports/M1_CLOSEOUT.md) 、[M2 报告](docs/reports/M2_VALIDATION.md) 、[M3 报告](docs/reports/M3_VALIDATION.md) 和 [M4 报告](docs/reports/M4_VALIDATION.md) 为准，其架构约束继续有效。

M2 浏览器验收需先启动带 `--browser-qa` 的 browser 服务及启用 Marionette 的无头 Firefox，再运行 `python3 tools/browser_m2.py`；死循环用服务端 `--fault infinite_loop` 与工具 `--expect-fault`，程序武器用服务端 `--robot-demo` 与工具 `--expect-weapons`。普通构建/测试不需要下载 Pyodide；HTTP 资源边界测试在未准备 bundle 的 CI 中显式跳过，真实浏览器证据单独记录。

M3 UI 验收使用独立临时编辑库启动服务和 Marionette Firefox，再运行 `python3 tools/browser_m3.py`；原生模式使用 `--url http://127.0.0.1:8765 --output docs/reports/m3-native-ui.json`。脚本会修改该测试编辑库，勿指向日常项目。

弹窗/固定视口回归：启动本机服务与 Marionette Firefox 后运行 `python3 tools/browser_dialog.py`，检查 F2/按钮/×、草稿保留、焦点与按键隔离，以及不同窗口尺寸下无页面滚动。截图与测量写入 `.m1-cache/dialog-*.png` 和 `.m1-cache/dialog-report.json`。
