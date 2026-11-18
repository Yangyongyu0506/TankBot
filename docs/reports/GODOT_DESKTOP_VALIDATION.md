# Godot 桌面原型验收

日期：2026-11-17。实现基线为 HEAD `7440e75` 加本轮工作区改动，未提交/推送。范围见 [44](../44_GODOT_DESKTOP_CLIENT.md)、[ADR-0056](../adr/0056-godot-desktop-presentation.md)。旧课程、预算、传感器、协议和历史报告未改写。

## 环境与实际范围

Godot 4.7.2 stable 官方 Linux x86_64 标准版，SHA-512 固定在 `config/desktop.yaml`。窗口实测使用 X11、OpenGL 3.3 Compatibility / NVIDIA RTX 5070 Laptop；无头使用 Godot headless。玩家代码使用原生 CPython/NumPy；没有启动浏览器或 Pyodide。只验证本机 Linux，不推断 Windows/macOS、其他 GPU、输入法或正式发行支持。

所有流程创建临时 settings/progress/Workspace/XDG 目录，服务器绑定随机 loopback 端口，C0预先完成作为C1解锁夹具，不用开发者绕过权限。测试算法只位于 `clients/godot/tests/integration.gd`，生产教学空模板保持原样。

## 已执行的客户端流程

- 授权快照插值、不外推、拒绝旧包、无位姿时不显示全局车体。
- F2全窗口编辑、高亮本关算法、源码语法错误及Python定位日志、修正后CAS保存。
- C1独立CPython测试Ready、另建正式Runtime部署Active、自动收起及运行期禁止F2重开。
- 玩家SE(3)输出进入授权视图；验收脚本只用授权估计/炮台编码器，经原人工炮台HTTP适配器瞄准，使用Space事件开火，真实裁判通关并写入隔离进度。
- 重试、自建文件保留、原始revision可读；访问C0实际键盘驾驶、切入无武器Navigation C0并返回Weapons，原算法和已有ledger条目逐字节保留。

首次访问此前未打开的关卡可追加模板来源ledger，合法产生新revision；不把“revision必须恒定”当成源码无损的判据。旧revision及其ledger仍可读取。窗口测试使用真实Godot GUI，但代码输入由测试驱动CodeEdit，不代表已完成真人中文输入法或长期可用性测试。

原始逐次 `flow.json`、Godot日志和截图保存在 `.m1-cache/godot-qa/`。机器可读最终摘要及可共享截图见本报告配套文件；无头流程不证明实际画面。

最终两种流程各28项检查通过，并实际调用 `tools/tankbot.py godot` 统一启动器，验证Godot自动退出后HTTP端口关闭。最终缓存分别为 `20261117T151904653325`（无头）和 `20261117T152053913799`（窗口）。数值摘要见 [JSON](godot-desktop-validation.json)，画面见 [游戏](assets/godot-desktop/game.png) 和 [全屏编辑器](assets/godot-desktop/editor.png)。

| 运行方式 | 总批次 / 有完成往返测量 | 往返p50 / p95 / p99 / max（ms） | 墙钟超时 / 错过门 |
| --- | --- | --- | --- |
| headless | 39 / 38 | 1.747 / 2.185 / 3.364 / 3.364 | 0 / 0 |
| X11窗口 | 110 / 110 | 1.743 / 2.340 / 2.519 / 3.150 | 0 / 0 |

这些是C1短流程的宿主墙钟观察，不是CPU配额或整局可靠性保证；少量样本不改变experimental状态。

## 检查记录

`tests/test_desktop.py` 的8项定向检查通过：CLI兼容、版本拒绝、下载摘要/只抽取固定成员、离线缓存/缺失处理、启动失败与正常退出清理。Godot流程通过统一入口的独立分组运行，标准Python/Node/Rust/文档/生成配置回归另记录于最终摘要。

| 实际命令 | 结果 |
| --- | --- |
| `python3 tools/check.py --offline` | 重跑退出0：398项Python、21个普通前端脚本/87项TAP、18项Rust、文档/Schema与生成配置一致性通过 |
| `.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_desktop.py -v` | 8项通过；标准运行已导入其中5项，后补3项下载检查另在本命令验证 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 退出0：28项无头流程、真实统一启动/退出检查通过 |
| `python3 tools/check.py --suite godot --offline` | 退出0：28项真实窗口流程、启动/退出、截图通过 |
| `npm run test:wasm` | 退出0：原生/WASM既有JSON ABI、课程、武器、轮电压和仓储快照对照通过 |
| `.m1-cache/learning-venv/bin/python docs/tools/check_design.py` | 文档、本地链接、26个Schema、50个正结构夹具及代码块检查通过 |
| `git diff --check` | 通过 |

标准检查日志为 `.m1-cache/godot-qa/standard-check.log`。本轮没有重跑Web端真人/Firefox编辑部署流程、长时Runtime候选基准或物理性能基准；不把保留Web入口和通过WASM对照描述成浏览器全流程重验。

## 本轮文件

| 路径 | 改动 |
| --- | --- |
| `clients/godot/` | project/main场景、HTTP适配、时间插值、授权绘图、原生编辑/部署/日志、独立集成脚本及Godot资源UID |
| `host/tankbot_host/desktop.py`、`cli.py` | 固定便携依赖、godot入口、进程清理与当前Authority退出处理 |
| `config/desktop.yaml`、`docs/schemas/desktop.schema.json` | 独立客户端参数和严格Schema |
| `tests/test_desktop.py`、`tools/test_godot.py`、`tools/check.py` | 生命周期/下载回归、隔离流程、统一独立检查分组 |
| `docs/44_GODOT_DESKTOP_CLIENT.md`、`docs/adr/0056-godot-desktop-presentation.md` | 当前原型合同、取舍和接受范围 |
| `README.md`、`docs/README.md`、`docs/02_SYSTEM_ARCHITECTURE.md`、`docs/10_DEVELOPMENT_ROADMAP.md` | 运行命令、架构和原型范围同步 |
| `docs/adr/0021-editor-and-deployment-profile.md`、`docs/adr/README.md` | 保留Web决策，链接桌面增量 |
| `docs/schemas/README.md`、`docs/tools/check_design.py` | 配置Schema索引及实际YAML验证 |
| `.gitignore` | 忽略Godot导入缓存；不忽略源码UID |
| 本报告、配套JSON与 `assets/godot-desktop/` | 当前证据和截图，不改写历史报告 |

## 保留的失败与修正

初始Godot导入受到沙箱的XDG写权限及本地socket限制，改用隔离XDG并显式授权运行检查。首轮CodeEdit属性名错误已修正为实际API `indent_automatic`；保存前显式读取编辑器当前文本，避免延迟信号造成漏保存。真实截图发现编辑器透出游戏画面，已增加不透明面板、等宽字体及文字对比度回归。

早期验收脚本只以J/L脉冲追求极小瞄准误差，部分窗口运行15秒内未击中，但没有Runtime故障或截止超时；最终脚本通过同一授权人工速度接口稳定瞄准，仍以真实Space事件发射。没有改物理、目标大小、命中规则或预算。跨C0的旧测试误要求整个revision恒定，现验证源码/原ledger/历史无损，保留模板来源追加的真实语义。两项下载测试初始mock未提供隔离ROOT中的配置，已修正夹具，8项重跑通过。

首次统一检查在Navigation规划回归处以SIGTERM中断，没有完成结果；完整日志重跑单独记录。不得将该中断当作通过。具有flow输出的失败保留于缓存；其他控制台失败及修正记于本节，未补造原始日志。成功重跑不抹去失败事实。统一启动的首轮隔离夹具把JSON科学计数法写进YAML后缀，导致既有YAML 1.1解析为文本；修正为JSON后缀后，实际启动、Godot自动关闭及HTTP停止检查通过，生产配置未变。

## 限制与下一步

尚非完整GUI迁移：没有Vim、补全/悬停、手柄、实验台/备份恢复面板、控制曲线、完整开发者图层和各导航专用图层。没有独立安装包或捆绑Python解释器的可执行发行物；统一源码启动可自动准备锁定Godot与现有Python依赖，缺Core时仍依赖Rust构建工具。现有Web功能继续保留。

Runtime仍是本人可信代码的普通独立子进程，不是OS强沙箱。30ms墙钟/20ms声明/6tick合同保持，状态仍experimental；少量C1批次和通关不证明整局截止可靠性。当前证据不包含全部十三关Godot通关、长时泄漏、Windows/macOS或浏览器Godot导出。
