# ADR-0010 固定 tick 与定点输出提交

- Status: Accepted
- Date: 2026-10-20
- Scope: Physics、传感器与 Runtime 调度

## Context

物理、传感器、Python 和渲染频率不同，消息异步到达；按到达立即改世界会使机器速度和网络成为隐藏规则。

## Decision

使用整数 tick 和固定 dt；传感器保留采样时刻与单独交付时刻。模块激活先冻结输入，输出固定在 activation + deadline 的提交门生效；早到不提前、迟到拒绝。Core 不等待 Python，实时/受控 Host 有明确预算，控制命令有 TTL。渲染只插值授权样本。

## Alternatives

可变 dt、物理线程回调玩家代码、消息一到就应用和用墙钟替代 sample time 均不采用。严格每 tick 等所有 Python 完成会使死循环阻塞全局。

## Consequences

跨模块产生可见延迟，但可解释、可测试、可录制。实时超时仍依赖硬件/调度，不能由固定步长推导跨机器确定性。

## Validation / Open Questions

测试同 tick 排序、时间公式、早/迟结果、乱序、reset、Host 超载；60/30/10/5 Hz 和预算是 Proposed 默认值，需基准确认。细节见 [07](../07_SIMULATION_DESIGN.md)。
