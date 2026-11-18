# Godot唯一玩家入口与浏览器退役验收

日期：2026-11-18。删除前基线为 `292cad36c31ad6a822c573c2faf7496f6a96e17a`，本轮未提交或推送。用户已确认同时移除Web/Pyodide，保留Godot必需API、原生Worker、headless/probe和Rust WASM开发能力；界面缺口明确待移植。决策见 [ADR-0057](../adr/0057-godot-only-player-entry.md)。

## 已实现的变更

- `python3 tools/tankbot.py`默认打开Godot，继续读取玩家current_level及前置条件；旧serve/browser/godot位置子命令和browser-qa参数拒绝。
- 删除Web GUI、CodeMirror/esbuild/npm包定义、Pyodide资源/适配器、浏览器Workers与专用工具/测试。LocalServer保留受控loopback API，网页和浏览器静态路由返回404。
- Core与独立CPython、SDK/Module接口、YAML课程、物理/评分、源码/进度格式不变。默认profile只发布native，30ms墙钟/20ms声明/6tick及独立规划预算不变，仍experimental。
- 构建/标准检查不调用Node/npm；独立WASM ABI工具迁至tools，显式WASM检查仍需Node。原生基准无浏览器资产依赖，历史JSONL分析仍可运行，不编造缺失依赖版本。
- 旧配置的browser字段和pyodide目录元数据允许结构读取但不提供执行后端；显式选择pyodide拒绝。JSON/Schema和生成配置同步。

## 兼容与已知界面缺口

课程、地图资产、底盘参数、玩家算法模板、revision/ledger/history、设置与进度不清空、不改写以适应删除。Godot当前仍缺曲线、实验台、工程维护/恢复面板、设置/改键、手柄、完整树与图层、高级编辑工具；相关后端API和数据保留。这是用户确认的范围取舍，不能声称已全部迁移。

历史报告/原始JSON保留当时计数、平台和配置。50处指向已删除源码的链接改为删除前提交的GitHub永久链接，涉及9份文档；仅修复引用，不改历史测量或结论。详细映射在 `.m1-cache/godot-only-qa/historical-link-repairs.json`。旧构建缓存未删除，但不再被游戏加载/提供。

## 文件范围

| 路径 | 本轮变化 |
| --- | --- |
| `host/tankbot_host/cli.py`、`server.py`、`management.py` | 默认Godot、删除静态Web路由/资源目录，保留受控本机API |
| `host/tankbot_host/browser_server.py`、`runtime/browser_authority.py` | 删除浏览器服务和Pyodide适配 |
| `web/`、`package*.json`、`config/browser-assets.lock.json` | 删除Web GUI、编辑器包定义和浏览器资源锁 |
| `tools/browser_*.py`、`prepare_browser.py`、`test_browser.py`、`test_frontend.mjs`、`build_editor.mjs`、浏览器基准HTML | 删除专用浏览器工具 |
| `tests/test_*.mjs`（除WASM）、`test_browser.py`、`test_frontend_entry.py` | 删除已退役界面专用测试；混合Python测试保留通用/原生部分 |
| `tools/build.py`、`check.py`、`.github/workflows/checks.yml` | 无npm标准构建/回归，Godot与WASM分组 |
| `tools/wasm_core.mjs`、`tests/test_wasm.mjs` | 私有WASM ABI测试适配器迁移，行为保持 |
| `tools/benchmark_runtime.py`、`calibrate_runtime_benchmark.py`、`summarize_runtime_benchmark.py`、Host基准助手 | 原生基准独立运行，历史浏览器结果只读汇总 |
| `config/game.yaml`、`runtime-profiles.yaml`、`runtime-benchmark.yaml`、对应Schema和生成夹具 | 删除活跃浏览器配置，保留明确旧配置结构兼容 |
| `clients/godot/main.gd`、`tests/integration.gd`、`tools/test_godot.py` | 启动提示、连接诊断、默认启动夹具和显式垂直同步测试选项 |
| `AGENTS.md`、根README、领域文档、ADR索引/0057和本报告 | 当前入口、退役范围、兼容及未移植能力说明 |

## 实际检查

- 桌面/CLI定向9项、Core构建定向4项通过：默认入口、退休命令拒绝、依赖摘要/离线、启动/退出与不调用npm。
- 原生profile/截止定向13项、进度树10项、原生规划准备2项通过，包括退休后端兼容拒绝、独立5秒准备预算及玩家字段不能放宽期限。
- `python3 tools/check.py --suite godot --offline -- --headless`通过；隔离证据 `.m1-cache/godot-qa/20261118T022751711193`。完成C1编辑/错误日志/修正/测试/部署/真实通关、C0驾驶、Navigation往返与源码保留，并实际验证默认CLI启动和窗口关闭后HTTP停止。
- `python3 tools/check.py --suite wasm`通过，复用原生/WASM动态快照、武器/全向/轮电压/仓储接触及JSON ABI对照。
- 原生基准计划检查通过；30ms空update短测目标2批、实际记录5批、0墙钟超时/0错过门。短测不构成可靠性验证，不调整预算。
- `python3 tools/check.py --suite godot --offline -- --disable-vsync`通过，真实X11窗口、33项检查及统一启动/关闭检查完成；证据 `.m1-cache/godot-qa/20261118T024428538928`。无头流程也通过33项；统一启动夹具不传子命令或level，使用无头自动关闭二进制验证默认读取新存档和退出清理。真实窗口流程使用测试脚本驱动控件，不冒充真人输入法验收。
- 配套 [机器可读摘要](godot-only-entry-validation.json) 和 [实际窗口截图](assets/godot-only-entry/game.png) 只包含隔离测试数据。headless C1记录69批、0墙钟超时/0错过门；X11诊断C1记录31批、0/0，不据此提高可靠性等级。
- `python3 tools/check.py --offline`最终退出1：388项Python中1项C6 DWA seed 2闭环超时；其余通过。入口正确传播非零，没有继续执行后续分组，因此本轮不宣称统一检查全绿。日志 `.m1-cache/godot-only-qa/standard-check-final.log`。
- 单独复测 `test_navigation_local.py` 的 `two_reference_methods_three_seeds_and_terminal_freeze`通过：1测试方法、两种方法×三个seed共六个场景，34.965秒；未改配置/算法/阈值。日志 `.m1-cache/godot-only-qa/navigation-c6-recheck.log`。
- 独立调用同一 `build.cargo_tool` 运行 `cargo test --locked --offline`，18项Rust通过；文档工具通过152份Markdown、26个Schema、50个正例、25个结构反例及代码块语法检查。`python3 tools/export_profile.py --check --offline`和`git diff --check`通过。

所有验收使用临时设置、进度、源码库、XDG目录和随机本机端口，不操作日常userdata。不运行浏览器或安装npm依赖。Linux以外桌面平台、所有十三关Godot流程、输入法和长期可靠性未验收；不因本轮删除升级平台/安全或experimental承诺。

## 失败记录和限制

保留首轮及重跑日志。退役代码专属测试随实现删除，通用权限、期限、规划、存档和历史测试保留；增加退休入口/静态资源404、legacy目录不可执行和原生规划预算检查，不能用删测试替代可用性验证。

首轮标准检查387项出现1错误、1失败：测试仍导入已删除browser_support，以及地图测试要求旧map-preview.js返回200。分别删除专用工具断言、改为404；原生基准的四项行为测试、地图API/权限/重试/练习进度四项重跑通过。日志 `.m1-cache/godot-only-qa/standard-check-initial.log` 保留，不将首轮记为通过。

X11/OpenGL NVIDIA窗口在默认垂直同步下重复未完成15秒Host握手，报告显示首请求仍在inflight；无头不复现。只限60FPS的诊断仍失败；临时禁用垂直同步后，限60FPS及不限FPS的两次完整流程均通过。失败输出分别保留于 `20261118T022957229237`、`20261118T023348554744`、`20261118T023435544510` 及后续同目录记录；成功为 `20261118T024305245139`、`20261118T024428538928`。这些结果提示显示呈现/调度相关性，但未完成驱动根因分析，不能宣称修复了默认图形环境。本轮不修改生产渲染参数，不提高Runtime墙钟或移动提交门。新增测试诊断参数 `--disable-vsync`，便于显式复现，不自动忽略失败。

最终统一运行中C6 DWA seed 2在tick7500到达120秒时限，实际路程4.830m、settled_ticks=0；没有碰撞、Runtime墙钟超时或错过门。失败与单独复测的首次生效tick分别为300/294，任务/path身份相同；准备时序和传感器流起点是后续调查方向，未完成根因确认。首轮统一运行中此项也曾通过。失败原始数据复制到 `.m1-cache/godot-only-qa/navigation-c6-regression-failed.json`，重跑另存 `navigation-c6-regression-recheck.json`，不以成功重跑覆盖失败。课程参考方法的时序敏感性仍需处理，不删除该回归、不提高120秒时限、不放宽局部导航要求。
