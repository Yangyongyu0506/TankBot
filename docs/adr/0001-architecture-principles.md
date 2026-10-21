# ADR-0001 纯核心与架构边界

- Status: Accepted
- Date: 2026-10-20
- Scope: 全系统逻辑依赖和贡献约束

## Context

同一游戏需要浏览器、桌面、无头和服务器运行；若 UI、Python 与物理共享隐式对象，信息权限和测试都会变得脆弱。

## Decision

采用纯 Game Core 与可替换 Host/Transport/Runtime Adapter。Core 仅处理固定步长物理、规则和已验证执行器输入，不依赖 UI、网络或 Python。玩家代码不可信，永不获得 World 引用或直接写物理状态。UI 只消费授权视图；跨平台与可测试性优先。不引入 ROS2/DDS 运行时依赖，不为过早优化绕过边界。

## Alternatives

完整前端引擎承担全部逻辑较快出画面，但损害权威与无头复用；强制统一进程结构无法适应服务器沙箱。二者不采用。

## Consequences

需要显式 DTO、Host 与适配层，初期代码比单体略多；可独立测试规则和权限。共享语义不代表目标平台已验证。

## Validation / Open Questions

无头 Core 不链接 UI/Python/网络；一套夹具跨 Adapter 验证；任何捷径不得绕过授权。技术库选择仍见 Proposed ADR-0002/0003/0013。详细设计见 [02](../02_SYSTEM_ARCHITECTURE.md)。
