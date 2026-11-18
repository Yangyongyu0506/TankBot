# 44 Godot 桌面客户端

## 目的与当前范围

Godot 4标准版/GDScript是当前唯一玩家GUI，使用原生CPython和Rust权威Core。无参数 `python3 tools/tankbot.py` 直接打开游戏；Web GUI、CodeMirror/npm、Pyodide/双Worker和专用浏览器工具已移除。用户确认的退役范围见 [ADR-0057](adr/0057-godot-only-player-entry.md)；[ADR-0056](adr/0056-godot-desktop-presentation.md)记录先前原型阶段，不再要求保留Web入口。

现有十三关的物理、算法接口、评分、权限和Workspace数据不变；客户端仍未具备所有历史Web界面功能，不能把保留后端能力说成完成Godot移植。

## 进程、职责与接口

```mermaid
flowchart LR
    L[无参数Python启动器] --> G[Godot GUI / Start / 日志]
    L --> A[Python Authority / 本机API]
    A --> C[Rust Core 权威物理]
    A --> P[独立CPython玩家Worker]
    G -->|管理请求 / token| A
    A -->|授权Profile / View / 日志| G
```

Godot使用既有 `GET /api/profile`、`/api/view`、`/api/workspace`、`/api/deployment`、`/api/campaign`、`/api/progress` 和 `/api/settings`。修改使用 `/api/workspace/*`、`/api/deployment/*`、`/api/campaign/*` 与人工执行器接口。服务仅绑定loopback，保留Origin、Host、控制令牌、JSON大小及频率检查；页面、编辑器bundle、浏览器Runtime配置等旧静态路由返回404。保留HTTP API不等于保留浏览器入口。

`backend.gd` 限制请求目标、并发、响应大小和超时；不等待玩家update。`timeline.gd` 使用simulation_tick插值、拒绝旧序号/版本，位姿跳变清理历史，无估计不显示车体，不外推断流。`world_view.gd` 只读取公开地图和获授权快照，map +y向上转换为屏幕+y向下，yaw不旋转相机。Godot刚体不是权威物理，玩家代码不持有Core/World句柄。

任务反馈文本仅变化时刷新，保留滚动位置；切关/重试后从顶部显示新任务。

## 外部编辑、Start与源码兼容

内置CodeEdit、源码文件树及保存/测试/部署按钮已按 [ADR-0058](adr/0058-external-editor-and-single-start.md) 删除。F2/VS Code按钮打开当前课程真实代码目录及主要文件，玩家保存后只需点击Start。Godot保留只读说明、升级预览、日志和停止操作，具体磁盘/版本接口见 [45](45_EXTERNAL_EDITOR_AND_START.md)。

Start自动生成原Workspace CAS快照，执行原独立检查，再创建全新正式Worker。失败显示Python日志；不以操作简化绕过检查、权限、规划准备或固定提交门。运行中可外部编辑，当前revision不变；停止后才能Start新版本。框架升级先捕获保存内容、预览/明确确认，再同步未修改文件，冲突拒绝并保留源码/历史。

文件保存在原userdata版本库的files目录，不迁移或清空原工程、ledger、revision或进度；游戏退出不关闭玩家VS Code。缺失编辑器时说明安装/PATH和实际目录，不恢复内置编辑器。选择课程载入准备场景，Start才运行保存代码。

## 配置与入口

`config/desktop.yaml` 和 [desktop Schema](schemas/desktop.schema.json) 管理Godot版本/官方包摘要、窗口、轮询及HTTP容量。仿真/模型/课程仍取原YAML，原生profile见 [41](41_RUNTIME_EXECUTION_PROFILES.md)。Linux x86_64首次缺Godot时在 `.m1-cache/godot/<version>/` 准备固定SHA-512便携包；离线须缓存完整或指定二进制。Python依赖使用原专用环境；缺Core时仅构建Rust，不调用Node/npm。

```sh
python3 tools/tankbot.py
python3 tools/tankbot.py --level c1
python3 tools/tankbot.py --godot-binary /path/to/godot --offline
python3 tools/tankbot.py headless --level c0 --ticks 600
python3 tools/tankbot.py probe --level c0
python3 tools/check.py --suite godot --offline -- --headless
python3 tools/check.py --suite godot --offline
```

`--workspace-store`、`--settings-file`、`--save-file`、`--map` 和 `--player/--developer` 含义不变。默认读取current_level并检查解锁，不自动开启开发者模式。`serve/browser/godot`位置子命令和 `--browser-qa` 拒绝；headless/probe仍是开发工具。关闭窗口后统一清理API、仿真和当前Worker，包括切关后替换的Authority。

## 检查与当前限制

标准入口自动发现Python回归，并检查Rust、文档/Schema和生成配置；不需要Node。Godot真实流程单列 `--suite godot`，使用临时设置/进度/工程/XDG和随机端口。Rust WASM构建/ABI对照为独立开发能力，`--suite wasm`才需要Node，不提供浏览器显示或Pyodide。

待移植界面：游戏专用矩阵实验（编辑能力交由VS Code）；控制/定位曲线；算法实验台；项目导出/备份/历史/清理管理；设置/改键、手柄与完整关卡树；完整开发者图层及导航专用可视化。有关后端API和数据仍保留，旧教材中的网页菜单/快捷键不代表已在Godot实现。用户明确选择本轮先清理，不同时补齐这些功能。

历史原型证据见 [2026-11-17报告](reports/GODOT_DESKTOP_VALIDATION.md)，本轮证据见 [退役验收](reports/GODOT_ONLY_ENTRY_VALIDATION.md)。Linux窗口证据不推断Windows/macOS、输入法、全部课程或正式发行能力。普通CPython子进程仍非OS强沙箱；30ms profile保持experimental，不因删除浏览器提高预算或可靠性等级。

本轮X11默认垂直同步下多次未完成握手；验收工具可用 `--disable-vsync` 仅对测试窗口禁用垂直同步，该诊断流程已通过。未将此选项设为游戏生产默认，也未据此确认GPU/显示服务器根因。无子命令启动/退出另以无头自动关闭夹具验证。
