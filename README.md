# TankBot

TankBot 将二维坦克运动、机器人算法学习与多文件 Python 编程结合。玩家通过传感器和自己的算法重建世界认知。

当前完成 **M1 + M1b 本机闭环原型**：Rust/Rapier2D 权威物理、差速/四轮径向全向轮底盘、理想轮编码器与质心 IMU、外部 Python 里程计、固定 tick 提交、Pose Selector、View Policy 和 Canvas 页面。M1b 增加双刚体炮台、单发/冷却、连续弹道/反弹/弹丸互毁、后坐/受击冲量、靶标与 Python 武器接口；M2 增加真实浏览器 Rust/WASM + Pyodide 双 Worker、独立 Runtime origin 与多 Adapter 验证；M3 增加 CodeMirror/Vim、多文件 Workspace、模板预览、快照测试、部署与回滚。尚无完整教学关卡或 Arena。

## 构建与运行

需要 Rust **1.99.1**、Python **3.11+**（本机实测 3.14.4）、Node.js **22+** 与 npm；WASM 探针另需 `wasm32-unknown-unknown`。编辑器使用 npm 锁定依赖。Python 依赖安装到自己的虚拟环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python3 tools/build.py
python3 tools/tankbot.py serve
```

打开 `http://127.0.0.1:8765`。差速：W/S 前后，A/D 转向。全向：W/S 前后，A/D 横移，Q/E 转向；启动时选择：

```bash
python3 tools/tankbot.py serve --chassis omnidirectional
python3 tools/tankbot.py serve --view weapons-practice
python3 tools/tankbot.py headless --ticks 600 --robot-demo
```

炮台 J/L 转动，空格或按钮单发（长按不连射）。默认估计视图隐藏真实弹丸，保留炮台与武器局部反馈；`--view weapons-practice` 明确授权显示真实车体、弹丸和靶标。Python 输入权限不增加。`--robot-demo` 使用独立的 [weapon_demo.py](examples/robot/weapon_demo.py) 控制炮台/开火，人工底盘仍可用；对应人工武器入口会拒绝。想观察程序控制可运行 `python3 tools/tankbot.py serve --robot-demo --view weapons-practice`。

所有可调模型、控制、场景及运行 profile 集中在 [config/m1.json](config/m1.json)，缺项报错，不补隐藏默认值。底盘只能在场景启动时选择。可在网页中保存、测试并部署 Python 项目；编辑与部署分离，成功部署不重置物理世界。示例算法在 [examples/robot](examples/robot/localization/odometry.py)，支持多文件 import，启动不会改写源码。

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

游戏界面固定在视口内，无需滚动网页。点击顶部「代码编辑器」或按 **F2** 弹出 Workspace；再次按 F2 或点击右上角 **×** 收起。草稿、光标与选中文件会保留。Workspace 支持 Python/JSON 编辑、Vim、文件切换、新建文件、Ctrl/⌘S 或 `:w` 保存。依次点击 **测试快照 → 部署已测试版本**；测试或候选启动失败会保留当前机器人。历史部署可显式回滚，产生新 Runtime 并清空算法状态，物理世界继续运行。编辑器焦点不会把 W/J/L/空格传给坦克。

默认编辑库保存在 `.m1-cache/workspaces/`，源码、模板 ledger 和测试/部署归档跨刷新保留。建议长期项目指定自己的持久目录，并定期导出备份：

```bash
python3 tools/tankbot.py serve --workspace-store /path/to/tankbot-project-store
python3 tools/tankbot.py browser --workspace /path/to/robot-seed --workspace-store /path/to/tankbot-project-store
```

`--workspace` 仅作为只读种子，不会回写玩家目录。模板更新和项目导入先展示旧模板/当前文件/新建议，默认保留已有文件；可按完整 revision 预览历史源码。重新启动使用启动示例，已保存草稿不会自动执行，须重新测试与部署。报告归档可导出，但不能绕过重新测试。

当前支持一个周期 Module 及其多文件依赖、`tests/test_*.py` 的 unittest；完整多模块图属于 M5。测试还检查语法/合同/权限和 6 个授权传感器仿真批次，测试输出不控制当前世界。原生测试只适用于本人可信代码；浏览器测试在独立 Runtime origin 的 Worker 中进行。细节见 [M3 设计](docs/17_EDITOR_AND_DEPLOYMENT.md)。

## 验证

```bash
cargo test --locked
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs  # Node 22+，浏览器表现行为测试
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

显示参数在 `config/m1.json` 的 rendering，默认练习缓存 80 ms、估计缓存 220 ms；差速 tracked 与全向 radial_omni 使用独立部件/颜色配置。配置内部版本现为 1.5，旧自定义文件需显式迁移轮组/显示及 browser/workspace 字段，启动不会自动覆盖。设计与浏览器证据见 [显示设计](docs/15_RENDERING_DESIGN.md) 和 [验收报告](docs/reports/RENDERING_VALIDATION.md)。

## 当前边界与设计入口

原生模式仅运行**本人可信的本机 Python**；普通子进程不是安全沙箱，不能开放第三方代码上传。UI 仅接收 View Policy 授权的估计/传感器或显式练习图层，不提供通用真值接口；本机设备所有者仍可通过文件/调试器读取自己的数据。实测为 Linux x86_64 原生和 Firefox 浏览器单机；Windows/macOS 构建 CI 已配置但尚无本次运行证据，其他浏览器与服务器隔离仍待验证。

从 [文档索引](docs/README.md)、[物理确认记录](docs/13_PHYSICS_MODEL_DECISIONS.md) 与 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 阅读。根 [AGENTS.md](AGENTS.md) 按用户要求保留原文件；其中“只有设计文档”的状态描述为历史基线，当前实现范围以本 README、[M1 收尾](docs/reports/M1_CLOSEOUT.md) 、[M2 报告](docs/reports/M2_VALIDATION.md) 和 [M3 报告](docs/reports/M3_VALIDATION.md) 为准，其架构约束继续有效。

M2 浏览器验收需先启动带 `--browser-qa` 的 browser 服务及启用 Marionette 的无头 Firefox，再运行 `python3 tools/browser_m2.py`；死循环用服务端 `--fault infinite_loop` 与工具 `--expect-fault`，程序武器用服务端 `--robot-demo` 与工具 `--expect-weapons`。普通构建/测试不需要下载 Pyodide；HTTP 资源边界测试在未准备 bundle 的 CI 中显式跳过，真实浏览器证据单独记录。

M3 UI 验收使用独立临时编辑库启动服务和 Marionette Firefox，再运行 `python3 tools/browser_m3.py`；原生模式使用 `--url http://127.0.0.1:8765 --output docs/reports/m3-native-ui.json`。脚本会修改该测试编辑库，勿指向日常项目。

弹窗/固定视口回归：启动本机服务与 Marionette Firefox 后运行 `python3 tools/browser_dialog.py`，检查 F2/按钮/×、草稿保留、焦点与按键隔离，以及不同窗口尺寸下无页面滚动。截图与测量写入 `.m1-cache/dialog-*.png` 和 `.m1-cache/dialog-report.json`。
