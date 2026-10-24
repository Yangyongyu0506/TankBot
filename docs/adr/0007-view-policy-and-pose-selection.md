# ADR-0007 View Policy 与显式位姿来源

- Status: Accepted
- Date: 2026-10-20
- Scope: Provider、Pose Selector、Gateway 与表现权限

## Context

系统定位要被玩家逐步接管，多个候选可能冲突；炮弹、相机、音频等也会暴露位置。

## Decision

玩家向独立候选 Topic 发布；Selector 唯一写标准位姿 Topic，显式选源，失效回退为 none。System Pose Provider 为 Authority 私有接口，使用需 grant。Gateway 在发送前处理所有表现通道，不向前端发送后隐藏。无全局估计时保留授权车体局部视图。

## Alternatives

最后到达者获胜不稳定；按真值误差选优构成定位 oracle；自动系统回退掩盖失败；客户端裁剪无法防作弊，均不采用。

## Consequences

需要来源、新鲜度、帧与插值规则；权限撤回必须清缓存。合法但错误估计继续显示，反馈不能偷偷携带修正量。

## Validation / Open Questions

验证多源切换、过期/跳变/错帧、局部可玩性以及效果/相机/音频旁路。Policy 具体格式和 UX 阈值未冻结，见 [04](../04_STATE_AND_VIEW_MODEL.md)。

## 2026-10-24 开发者角色增量

[ADR-0026](0026-settings-modes-and-campaign-progress.md) 增加 Authority 侧显式开发者只读 grant 与独立 DeveloperSnapshot；它构成额外角色的视图权限，不能改变玩家快照、估计 Topic 或 Python 输入。显示偏好只能隐藏/显示已授权数据，不能授予真值；退出开发者须清除该角色的显示缓存。
