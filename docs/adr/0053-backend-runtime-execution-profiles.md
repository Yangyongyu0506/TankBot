# ADR-0053 后端运行profile、声明准入与墙钟截止

- Status: Accepted
- Date: 2026-11-06；2026-11-07接受本机实现合同
- Scope: 本机CPython与Pyodide；不改变物理、算法dt、权限或activation + 6tick

## Context

旧runtime.batch_budget_ms同时限制Contract预算总和与整批往返。历史评估提出原生30ms、浏览器50ms，但未执行候选看门狗长测，不能作为既定默认。浏览器接收检查尚未覆盖响应解码期间跨越截止，原生管道写入也可能阻塞Authority线程。

## Decision

使用config/runtime-profiles.yaml的版本化目录，分离共同module_declared_budget_cap_ms与各后端batch_wall_deadline_ms。可信Worker工厂声明后端，Authority在创建尝试时选择不可变profile，所有测试、部署及回放Worker继承同一冻结对象；普通请求和遥测不参与选择。

旧batch_budget_ms独立出现时，两种限制都等于旧值。新旧配置模式互斥，即使数字相同也拒绝混合；不存在静默优先级。新配置以20/20为基线实际对照后，选择原生30ms、浏览器40ms，声明总上限仍20ms；两个profile均保持experimental。Accepted针对配置、冻结及截止合同，不表示已证明整局失败率<1%。

使用Authority时钟域的整数单调纳秒，从开始编码到完整接收/JSON解码后检查，恰好截止合法、刚超限拒绝。看门狗延迟不会使迟到结果合法；iframe只负责局部终止，桥接时间只作诊断。结果仍必须在原固定门通过关联、权限及语义验证。原生写管道转到有界单请求的专用线程，不等待玩家读取；受控测试可在既定预算内等待，实时物理不等待。

有界逐批事件流独立于UI滑动窗口；基准工具流式保存、分文件限额、汇总同批update总和与截断/尝试失败，不导出传感器、真值或无关源码。正常/负载、冷启动/首次激活/稳态分别报告，候选真实执行，不按旧直方图推断通过。

## Alternatives

直接把batch_budget_ms改成50会扩大准入；只信iframe时间遗漏双向排队；浮点误差宽限会增加未声明预算；逐模块硬配额需要更强隔离，不属于本任务。仅用p99或一次零失败确定默认值不充分。

## Consequences

需要更新Supervisor、浏览器桥、配置/Schema、环境摘要、公开诊断及回归。模块内部遥测仍不可信，声明上限不是硬CPU配额。默认值选择必须引用新实测；若不足以证明整局故障率<1%，明确标实验性。细节与验证计划见 [41](../41_RUNTIME_EXECUTION_PROFILES.md)。

## Evidence 与局部修订

当前实现、最终96格逐批矩阵、两后端完整UI和配置/时间边界回归见 [实际验收](../reports/RUNTIME_EXECUTION_PROFILES_VALIDATION_20261107.md)。局部修订ADR-0010/0020/0031/0051/0052中本机共享预算字段和当时20ms常量；其固定tick、权限、物理、课程评分和玩家源码保留规则继续有效。初测、中断及最终矩阵分开记录，未把不同源码混合提高置信度。默认仍需跨会话、更多整局及其他平台验证；不宣称服务器隔离或Arena公平性。
