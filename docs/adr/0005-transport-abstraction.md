# ADR-0005 Transport 无关的协议

- Status: Accepted
- Date: 2026-10-20
- Scope: In-Process、Worker、IPC、WebSocket、Replay/Test

## Context

部署结构不同，但信息边界和时间含义必须相同；把 WebSocket 连接本身当协议会妨碍本地与无头复用。

## Decision

采用有界 send/receive/close 接口，语义层统一验证 Envelope、权限、run 和时序。WebSocket 用 JSON 帧，IPC 用长度前缀，Worker 用规范 DTO，进程内用不可变拷贝，Replay 注入记录的交付序列。send 成功仅表示入队，不代表执行成功。

## Alternatives

所有场景走 WebSocket 简单但引入不必要 loopback 网络；各平台自定义消息语义容易产生旁路。只共享接口/语义，不强制同编码内存布局或进程拓扑。

## Consequences

需要 Adapter 一致性测试；“本地”不能跳过权限。背压导致显式拒绝/丢旧 Topic，不能阻塞物理。

## Validation / Open Questions

用相同正反夹具测试顺序、边界、断线、重置、队列满；实际 IPC 选型和网络恢复窗口后续测量。细节见 [03](../03_PROTOCOL_SPECIFICATION.md)。
