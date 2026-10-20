# ADR-0006 三层状态与唯一物理权威

- Status: Accepted
- Date: 2026-10-20
- Scope: Ground Truth、Estimated State、Player View

## Context

估计误差本身是学习内容，若估计覆盖真实状态或偷偷矫正到真值，将破坏玩法和公平性。

## Decision

World 仅由 Core 写入；玩家估计独立存储，不能改碰撞/命中。Runtime 只获授权测量。Player View 是 Authority 生成的 DTO，任何调试/评分真值走独立受信路径，不能回灌正式算法。

## Alternatives

共享 World 并靠自律隐藏、用 CSS 隐藏真值、按估计移动物理坦克、用真实位姿校正 UI 均不采用。

## Consequences

屏幕估计可能与真实碰撞不同，必须标明来源并提供局部反馈；多层状态增加存储/调试复杂度，却保留核心教学机制。

## Validation / Open Questions

给合法估计施加偏移时碰撞和计分不变；禁用系统源后抓包/SDK 无真值；评分器输入与 Runtime 输入分离。离线设备所有者可逆向内存的限制必须明示，见 [04](../04_STATE_AND_VIEW_MODEL.md)、[08](../08_RUNTIME_AND_SECURITY.md)。
