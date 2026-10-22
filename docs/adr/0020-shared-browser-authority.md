# ADR-0020 浏览器复用 Authority 与独立玩家运行区

- Status: Accepted
- Date: 2026-10-22
- Scope: M2 本地浏览器部署与适配；不接受服务器沙箱技术

## Context

M1 已有 Python Authority 的 Schema/语义权限、固定提交门和 View Gateway，以及 Rust 纯 Core。M2 必须运行浏览器 WASM/Python 完整闭环，并使平台 Adapter 共享规则。只把物理编译成 WASM 不能解决另一套权限实现的漂移。

## Decision

通过可信工厂注入 Core/Runtime Adapter，在 Core Worker 的 Pyodide 中运行同一份 Authority；它调用 Rust WASM 的私有 JSON 槽 ABI。玩家 ModuleRunner 在另一 Pyodide Worker 执行，只加载 SDK/协议构造代码和部署源码。双 origin iframe 持有可终止玩家 Worker 的可信桥；主 UI 仅有控制请求和授权视图接口。Rust Session 与 Python ModuleRunner 分别在两平台共享，物理/协议/SDK 消息不分叉。

采用锁定 Pyodide 0.29.5、只读资源白名单、CSP、定点提交与外部终止。Robot 使用已验证的 classic Worker 路径，保留 `worker-src 'none'`。同一 49 个协议夹具在 IPC/WebSocket/In-Process/Replay 和浏览器 Authority 产生同样结果。

## Alternatives

JS Authority 减少启动/内存，却需重复安全规则与一致性维护；Rust Authority 可减少语言边界，但迁移现有验证器扩大 M2；嵌入玩家 Python 到 Core Worker 破坏故障隔离；所有平台统一进程布局限制原生无头能力。当前保留小 Adapter，让后续优化以实际数据为依据。

## Consequences

两个解释器增加下载/内存与转换成本；可信 Authority tick 的长尾接近 60 Hz 时间预算，多机器人前必须测量。单机器人本机数据见 [M2 验收](../reports/M2_VALIDATION.md)，接口与限制见 [16](../16_BROWSER_RUNTIME.md)。所有控制和物理参数仍在唯一配置，内部配置升级 1.4，公共消息不变。

浏览器没有 cgroups 等价的硬内存/CPU/存储额度，本地设备所有者可检查启动资源；不声称可在本地保密或保证 Arena 公平。ADR-0013 的完整平台安全组合仍为 Proposed。未来移植 Authority、换 Pyodide 或放宽 CSP 均须新增证据和 ADR。
