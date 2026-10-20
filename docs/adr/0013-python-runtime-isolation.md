# ADR-0013 Python Runtime 平台隔离组合

- Status: Proposed
- Date: 2026-10-20
- Scope: Pyodide、CPython worker 与服务器沙箱选型

## Context

算法属于不可信代码，需要防死循环、资源耗尽、文件/网络访问与跨机器人读写。浏览器、本机和服务器的能力不等价。

## Decision

建议浏览器使用独立 Pyodide Worker，Core 位于另一 Worker；本地原生用外部 CPython worker，按已验证能力标注运行限制；服务器评估 gVisor/microVM 等强化隔离及 OS 资源控制。所有方案统一走 Supervisor/Router，不把 SDK、Python 线程或普通 subprocess 当充分沙箱。

## Alternatives

嵌入 CPython 简化调用却破坏故障/安全边界；过滤 builtins/AST 不可靠；普通容器较轻量但不能替代完整威胁评估；microVM 更强隔离带来启动/内存成本。具体取舍需实验。

## Consequences

不共享进程内对象，必须序列化；每机器人独立故障域，恶意模块可能拖垮本机器人但不能阻塞 Core。禁止真值访问、资源配额和不开放未隔离第三方代码是 ADR-0001/0006 的强制约束，不因本技术 ADR 是 Proposed 而变可选。

## Acceptance Gate / Open Questions

提交平台安全矩阵、网络/文件/CPU/内存/进程攻击测试、强杀与恢复、冷启动/数学库基准。浏览器独立 origin/CSP、桌面 OS 限制与服务端方案分别验证，允许分平台接受，不宣称一个 Worker 覆盖所有保证。见 [08](../08_RUNTIME_AND_SECURITY.md)。
