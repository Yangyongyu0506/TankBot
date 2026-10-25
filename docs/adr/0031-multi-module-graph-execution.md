# ADR-0031 多模块图沿用冻结输入与固定 tick 提交

- Status: Accepted
- Date: 2026-10-25
- Scope: M5；实现 ADR-0008/0010/0012 的本机多模块子集

## Context

M4 只有单 Module 包装。C3/C4 需要复用坐标变换、跟踪和自瞄，又不能让模块调用顺序改变输入、绕过权限或提前控制物理。

## Decision

一个机器人共享一个隔离 Runtime，Manifest 显式连接类型化 Topic，单写者，依赖只决定 setup/reset 顺序。稳定 ID 调度同步周期/event 模块；每批冻结输入，延迟固定 6 tick 提交；模块输出分组原子校验。reset 使用实际部署 origin，部署/回滚重建整图，候选测试用独立缓存。

模块预算总和受 YAML 机器人预算限制；硬终止仍以整个批次为单位。公开图与 Topic 通过 Authority/View Policy，不增加真值权限。完整接口见 [26](../26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)，准入、时钟与回滚实证见 [验收](../reports/M5_VALIDATION.md)。

## Alternatives

同回调直接路由输出会让 stable ID 改变算法输入；每模块进程增加启动和通信成本；任意异步 await 缺乏可重现时钟。先采用固定延迟共享 Worker，不声称具备 ROS2/DDS 功能。

## Consequences

模块链具有明确管线时延，算法需保留采样 tick。死循环影响整台机器人而不阻塞 Core；模块内部不是安全边界。逐模块抢占、持久检查点和动态增删图仍未实现。任何扩展不得改变已发布消息含义。
