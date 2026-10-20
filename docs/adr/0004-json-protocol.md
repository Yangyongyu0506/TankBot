# ADR-0004 轻量 JSON 协议

- Status: Accepted
- Date: 2026-10-20
- Scope: 通信语义、结构验证与版本治理

## Context

玩家需要类型化 SDK，系统需要跨语言/平台和可录制输入；引入通用机器人中间件会增加部署和教学负担。

## Decision

采用 JSON Envelope，定义 Topic、Command、有限请求响应 Service 和 Event；使用 JSON Schema Draft 2020-12 描述结构，领域验证处理数值/时间/坐标/权限。版本、单位、序列与资源上限显式化。初期不引入 Action、DDS 或 ROS2。首次发布前冻结 v1 草案，发布后不破坏同 profile 兼容。

## Alternatives

直接暴露 JSON 给玩家增加样板；ROS2/DDS 超出需要；二进制编码可后续根据 profile 引入，但不得改变语义或削弱校验。

## Consequences

日志可读且便于夹具测试；编码分配有性能成本，先测量。Accepted 的是轻量语义与版本原则，不表示 1.0 草案字段、预算或所有频道已发布。

## Validation / Open Questions

Schema 正反例、权限/时序负例与兼容性回归为发布门。频道注册表和例子见 [03](../03_PROTOCOL_SPECIFICATION.md) 与 [Schema](../schemas/README.md)；编码优化由实际负载决定。
