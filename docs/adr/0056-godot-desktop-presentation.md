# ADR-0056 Godot 桌面表现与统一原生启动原型

- Status: Accepted
- Date: 2026-11-17
- Scope: 用户确认的 Linux 桌面原型；不表示完整客户端迁移或发行验收
- Amends: [0021](0021-editor-and-deployment-profile.md) 的前端适配范围；Web 入口继续保留

2026-11-18局部修订：[ADR-0057](0057-godot-only-player-entry.md) 删除Web/Pyodide和旧玩家子命令，当前仅Godot＋原生CPython；本记录的原Context和历史证据保留，其他仍适用的权限、Workspace或截止合同不变。

## Context

现有 GUI 使用浏览器；原生模式实际上已由 Python Authority、Rust Core 和独立 CPython Worker 执行仿真与玩家代码。用户希望改用 Godot，并已明确确认“合并环境”指统一安装和启动，仍保留独立玩家 Worker。首轮明确为 Godot 4 标准版/GDScript、授权渲染、键鼠、F2 多文件编辑、测试/部署和日志；Web 保留回归。

## Decision

增加 `godot` 启动模式与 `clients/godot/`，复用原生 LocalServer 的现有管理接口及 Authority。Godot 不运行 Pyodide，不嵌入玩家 Python，不拥有物理、传感器、裁判或 Workspace 文件的写入权。既有 Origin/Host/control-token 校验保留；客户端只连接启动器指定的 loopback 地址。

统一启动器复用专用 Python/NumPy，发现 Godot 或准备 SHA-512 固定的便携 Godot；缺少 Core 时仅构建 Core，不构建 npm/Web 资源。窗口结束由启动器关闭 HTTP、仿真和当前玩家 Worker。源码、稳定关卡 ID、工程 scope、CAS、ledger/history、测试环境绑定和固定 tick 提交均不变。原生 profile 仍为 30ms experimental，声明额度为20ms；不以 GUI 替换为由提高预算。

Godot 使用已有授权快照的时间插值，XY 相机跟随所选显示位姿、世界方向固定；没有合法位姿就不显示全局车体。原生 CodeEdit 仅为原型编辑器，不能声称已具备 CodeMirror/Vim、补全和类型工具的完整等价能力。

## Alternatives

把 Python 嵌入 Godot 同进程会削弱外部死循环终止/故障边界，用户明确未选。直接改用 Godot 物理会更改课程动力学、传感器与评分，超出本轮。WebView 复用编辑器会保留浏览器依赖，首轮采用原生 CodeEdit。直接删除 Web 会丢失现有浏览器运行与回归能力，暂不采用。

## Consequences / Validation

增加 Godot 运行依赖和独立检查分组，但原型不需要 npm/Pyodide；开发机缺 Core 时仍需 Rust 工具链。统一源码启动不是已完成 Windows/macOS 安装包，也不等同于捆绑解释器的独立可执行发行物。原型只运行本人可信代码，原生子进程仍非强沙箱。产品范围与实际验证见 [44](../44_GODOT_DESKTOP_CLIENT.md) 及 [原型验收](../reports/GODOT_DESKTOP_VALIDATION.md)。完整编辑器、手柄、实验台和跨平台导出后续分别验收；不因本轮通过升级 Runtime 可靠性或 ADR-0013 状态。
