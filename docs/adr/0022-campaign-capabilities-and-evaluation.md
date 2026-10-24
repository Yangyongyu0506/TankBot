# ADR-0022 关卡能力配置与结束后评分

- Status: Accepted
- Date: 2026-10-23
- Scope: M4 Campaign、Radar 与目标估计

## Context

C0–C2 需要渐进撤回敌方真值并保留自定位；教学代码必须跨关保留。活跃期真值误差可被反复查询成定位 oracle。

## Decision

采用受信 Campaign 配置切换 Authority 能力。前三关保留经 Pose Selector 路由的系统自定位；Radar 从私有世界 DTO 生成授权测量。目标估计使用独立 Topic 和 `target_estimate@1`，保持自身 Pose Selector 的单写者职责。函数/类包装共享 Contract，新增模板只补缺失文件，阶段 ledger 独立。开始关卡建立新纪元；详细评分仅在停止本次 Runtime 后发布，物理与已有弹丸继续。

用户确认的 Radar、巡逻和血量模型集中在单文件配置。C2 敌车与玩家共享同一 Rapier World 和速度伺服，实现真实接触与受击；3 HP 归零后移除刚体/碰撞并通关。C2 以击杀结果为准，误差作结束后诊断；授权 HP 不携带敌车坐标。视图新增显式 `view_snapshot@3`，保留旧版本。

## Alternatives

客户端隐藏敌车、每关复制仿真、每 tick 返回真值误差和覆盖原算法模板都会破坏现有边界或代码延续性。

## Consequences

需要明确关卡生命周期、估计新鲜度和非覆盖解锁；C2 必须通过两种算法验证。浏览器由设备所有者控制的本机安全限制仍适用，不据此声称 Arena 防作弊。

## Evidence / Acceptance

模型已由本轮用户逐项确认。[M4 报告](../reports/M4_VALIDATION.md) 记录原生/Firefox 实际三关通关、编辑与跨关保留；[Campaign 测试](../../tests/test_campaign.py) 运行两种跟踪方法、权限/时序/评分和模板负例；Rust 测试量测动量、质量、销毁与巡逻。接受范围为已验证的本机 profile，其他平台、完整课程及 Arena 仍须后续验证。
