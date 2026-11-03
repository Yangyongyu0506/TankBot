# ADR-0045 独立课程工作区

- Status: Accepted
- Date: 2026-11-02

## Context

用户要求下一章节 Navigation 只做底盘运动，不复用 Weapons 算法。ADR-0040 的固定 campaign scope 避免了跨关卡源码失踪，但也把未来所有课程放进同一工程。不能通过删除或重置旧工作区实现课程隔离。

## Decision

在关卡声明可选 scaffolding.workspace_scope。省略时保留原 campaign 身份与 C0–C5 默认存储目录；新的稳定 scope 使用独立版本库，同课程内跨关卡复用。scope 仅决定项目管理，不决定仿真、控制权或权限。

不同 scope 的解锁不能向当前库叠加模板。新的 scope 不自动搜索/复制旧 Campaign profile。原有源码、revision、ledger、archive 与通关记录保持；--workspace-store 仍为显式选择，不以清空已有工程来保证“干净”。服务端和浏览器启动器需要在切关时选择正确工程，并原子切换 Authority/Workspace。

## Alternatives

删除 Weapons 文件会损坏用户算法与历史；每关一个工程会丢失后续底盘课程的渐进开发；继续共用工程容易执行旧测试和混淆可编辑文件。稳定的课程 scope 是对 ADR-0040 的管理范围细化，而非恢复按运行接口计算目录。

## Consequences

默认 Campaign 身份完全兼容。独立项目占用额外存储；切关的测试/部署状态必须清理并与项目身份绑定。显式选择同一外部工作区不应触发自动删除；需要说明其为用户主动选择。

## Validation / Status

存储分组、Schema、跨 scope unlock 拒绝及两个启动器的 select_workspace 已接入。原生和浏览器真实网页均已完成独立项目、测试/部署、重试、章节往返以及 Weapons 原快照/历史相等检查，证据见 [Navigation 验收](../reports/NAVIGATION_CONTROL_VALIDATION.md)。电机模型由独立的 [ADR-0046](0046-confirmed-wheel-voltage-control.md) 记录，不由本 ADR 隐式接受。
