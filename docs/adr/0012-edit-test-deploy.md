# ADR-0012 快照测试与不可变部署

- Status: Accepted
- Date: 2026-10-20
- Scope: 编辑、测试、部署与运行状态

## Context

多文件编辑、Python import cache 和热更状态容易让“通过测试的代码”与“正在运行的代码”不同，也可能在部署失败时破坏旧机器人。

## Decision

采用 Edit → Test → Deploy。报告绑定 Workspace revision/摘要和运行 profile；artifact 内容寻址且不可变。新 Runtime 完成安全导入/setup 后在 tick 边界原子切换，状态默认重置。失败 staging 保留旧部署；回滚创建新部署实例，不回滚物理世界。测试与评分真值不注入正式 Runtime。

## Alternatives

保存即热更新体验快但难以追踪，多文件部分加载和跨版本状态迁移有隐患；直接在 Host import 玩家文件不安全。默认不采用。

## Consequences

需要报告/快照存储和部署阶段；不保证无感状态续接，但语义清晰可重现。跨版本 checkpoint 迁移需显式函数与测试，禁止任意 pickle。

## Validation / Open Questions

编辑/测试摘要不一致、导入失败、原子切换、旧消息/租约、显式回滚、重置/部署区别和沙箱测试路径均需覆盖。见 [06](../06_WORKSPACE_AND_TEMPLATES.md)。
