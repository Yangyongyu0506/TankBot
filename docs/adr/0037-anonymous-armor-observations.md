# ADR-0037 C5 匿名装甲观测与等价朝向

- Status: Accepted
- Date: 2026-10-26
- Scope: 局部修订 ADR-0035 的 C5 传感器与估计，不改 C0–C4

## Context

用户认为 C5 的“截获车头 GPS + 中心 Radar”叙事牵强，要求只观测最近两块装甲的己方车体系距离/方位。用户进一步确认可见性、10 Hz/12 m、σr=0.03 m、σθ=0.005 rad、逐块 10% 丢失和匿名/模 90° 朝向规则。

## Decision

用注册的 armor_detector、armor_detections@1 和只读 NumPy ArmorDetections 提供当前 0/1/2 行 [r,theta]；先筛选量程、朝向和墙体，再选最近、丢失、加噪。等距不按物理编号排序，不提供敌车中心或 GPS 观测。所有数值、权限、合同与说明由 C5 YAML 声明。

玩家在新 armor_tracker.py 估计中心和等价装甲相位，再复用独立预测/控制接口。四重对称不允许恢复唯一真实车头，yaw RMSE 使用 YAML period_rad=π/2；通关仍以存活击杀为准。现有位姿输出和消息保持兼容，C4 GPS 与 2π 朝向语义保持。

后续 [ADR-0038](0038-center-target-auto-aim.md) 调整 C4 为中心自瞄，撤销 GPS；C5 的匿名观测、等价朝向与本 ADR 模型保持。

## Alternatives

提供装甲 ID 可消除部分关联困难，但超出“仅极坐标”要求；强制每帧补两块会返回遮挡或虚构数据；沿用大中心 Radar 噪声会严重混叠约 0.30 m 间距的装甲。继续用 2π 评分会惩罚不可区分的等价姿态。均不采用。

## Consequences

新增受限消息类型、传感器、模板和可视化适配；C5 管理脚手架升为 4.0.0，旧算法和历史按既有非覆盖流程保留。玩家需处理换板、缺测和相位绕回，不能依赖固定行号。多目标、真实图像识别与非对称模型不在本轮范围。

## Validation

接受依据为用户逐项确认。几何、匿名对称、Schema/SDK、权限、无损迁移与闭环证据见 [30](../30_ARMOR_OBSERVATIONS.md) 和 [验收报告](../reports/ARMOR_OBSERVATIONS_VALIDATION.md)；不宣称验证所有平台或教学效果。
