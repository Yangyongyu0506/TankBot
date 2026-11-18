# ADR-0057 Godot 唯一玩家界面与默认入口

- Status: Accepted
- Date: 2026-11-18
- Scope: 移除浏览器显示/Runtime，保留原生仿真、开发工具和数据兼容
- Supersedes: [0020](0020-shared-browser-authority.md) 的浏览器部署架构
- Amends: [0021](0021-editor-and-deployment-profile.md)、[0056](0056-godot-desktop-presentation.md) 的Web界面保留；[0053](0053-backend-runtime-execution-profiles.md) 的活跃后端集合

## Context

Godot原型已经能够连接原生Authority、编辑/测试/部署并运行CPython算法。继续维护Web GUI、CodeMirror/npm、独立origin/Pyodide和浏览器工具形成两套客户端成本。用户明确要求删除浏览器功能，并逐项确认：一并移除浏览器Runtime和专用工具；Web独有界面功能列为待移植；保留headless/probe和Rust WASM开发能力。

## Decision

`python3 tools/tankbot.py` 无参数直接启动Godot，仍接受关卡、地图、设置、存档及Workspace参数。`serve`、`browser`、`godot`不再是玩家子命令；`headless`、`probe`作为可选开发命令保留。无参数时遵守原玩家解锁和current_level存档，不自动开启开发者模式。

删除Web页面/脚本、CodeMirror/esbuild/npm包定义、Pyodide资源锁、BrowserServer/BrowserSupervisor、双Worker/origin桥及专用浏览器验收工具/测试。LocalServer仅提供Godot所需的loopback API，静态网页和浏览器启动资源路由返回404；Host/Origin/token、权限和容量保护保持。WebSocket协议Transport是通用协议组件，继续保留，不是Web GUI。

原生CPython仍独立Worker；Rust/Rapier仍是权威物理。20ms声明准入、原生30ms experimental墙钟、6tick门及独立5秒规划不变。默认profile目录只发布native；旧配置中的browser字段及pyodide目录元数据仅作结构兼容，不存在可启动的Pyodide后端，显式选择拒绝。应用配置2.1、协议、SDK和玩家文件接口不作破坏性修改。

日常构建/标准检查不调用Node/npm。Rust WASM构建及JSON ABI对照保留为独立Core开发检查；其Node运行器从web目录迁至tools，只在显式WASM检查时需要Node。原生基准继续使用隔离场景和有界事件流，历史浏览器报告仍可只读分析，不要求已移除的运行资源。

## Alternatives

仅隐藏旧命令但保留全套页面和Workers无法消除维护成本，未采用。先补齐Godot所有曲线/实验/维护面板会扩大本轮范围，用户选择后续移植。删除全部HTTP或WASM会破坏Godot管理或独立Core验证，用户明确选择保留这些开发能力。把Python并入Godot进程会改变故障边界，不属于本轮。

## Consequences / Validation

Godot当前没有完整Web功能等价：手柄、设置/改键界面、关卡树布局、智能编辑工具、曲线、实验台、备份/清理面板和部分导航/开发者图层待移植。其后端合同、已保存数据和课程算法继续保留；不通过删除源码或更改评分掩盖界面缺口。

历史报告/JSON保留当时事实。指向已删除源码的文档链接改为删除前提交的永久链接，避免把历史记录伪装为现行可运行工具。当前范围见 [44](../44_GODOT_DESKTOP_CLIENT.md)，实际命令、原生/WASM/Godot结果及限制见 [本轮验收](../reports/GODOT_ONLY_ENTRY_VALIDATION.md)。未执行的跨平台/全部课程玩家流程不算通过，Runtime profile可靠性和服务器沙箱状态不升级。
