# ADR-0028 有界玩家运行反馈

- Status: Accepted
- Date: 2026-10-25
- Scope: 玩家 print、异常与 UI 日志，不扩展真值权限

## Context

用户需要在运行时 Web UI 查看日志并调试 Python。此前 stdout 被重定向但原生 stderr 丢弃，浏览器输出 callback 为空；异常常只有 MODULE_ERROR，缺少可定位反馈。

## Decision

原生独立读取 stderr，浏览器使用有额度的固定 log 旁路；Supervisor 与 Authority 分别有字节/条数上限。Authority 为玩家输出附加来源、模块、部署版本与接收 tick，通过 Deployment 管理状态给 HUD/编辑器面板。保留 traceback、项目行号跳转、来源筛选、清空显示和 Runtime 故障状态。

后续调试反馈修订：单元测试直接输出标准 unittest 详细日志，不丢弃失败调用栈；面板按来源/模块/部署连续展示原始文本，并在测试与失败时展开。管理状态保留机器错误码，另从相应快照的输出提取 Python 异常摘要与项目行号；不通过日志扩大玩家数据权限，也不改写玩家源码。详见 [24](../24_RUNTIME_LOGS.md)。

## Alternatives

依赖浏览器开发者工具或宿主终端不能满足游戏内反馈。把日志直接写进物理状态/标准估计 Topic 会破坏职责；无上限保存会随运行增长。完整交互 debugger 成本高，暂不作为本轮日志需求。

## Consequences

日志不持久化，不承诺精确采样时刻；过量输出会裁剪并计入执行预算。面板只读玩家 Runtime，不暴露 Authority World。当前草稿与运行快照可能不同，定位须提示版本。原生路径处理与其他浏览器仍需平台验证。

## Evidence

实现与额度见 [24](../24_RUNTIME_LOGS.md)，print、测试输出、运行异常、源码跳转、错误后恢复及两种运行方式证据见 [验收](../reports/PLAYER_RUNTIME_VALIDATION.md)。
