# ADR-0016 按轮名发布理想编码器观测

- Status: Accepted
- Date: 2026-10-21
- Scope: M1 轮组传感器、SDK 值类型与既有 encoder 兼容性

## Context

四轮麦克纳姆不是左右两轮，旧 `encoder@1` 的累计米制左右轮距不能自然表达。用户希望接口尽量沿用 ROS 习惯，不能以虚假左右轮距离掩盖全向自由度。

## Decision

新增 `/robot/sensors/joint_states` / `joint_state@1`，字段 `name,position,velocity,effort` 对应轮名、累计角（rad）、边界角速度（rad/s）、可选转矩（N·m）。M1 effort 为空，因为未建模独立电机。所有数组必须与 name 同序；position 长度相等，velocity/effort 允许空，否则长度相等。Schema 验形，Host 验跨数组与权限。

差速轮名为 left/right，麦轮固定 front_left/front_right/rear_left/rear_right；frame 为 base_link，tick 在 Envelope，SDK 为不可变 `JointState`/`Sample[JointState]`。旧 encoder@1 与 EncoderData 的米单位/语义不变，M1 默认不发布旧频道。增加注册类型不会改变原有类型；协议未发布草案，发布前冻结协商支持集。

## Alternatives

四个命名固定字段缺乏后续轮组扩展性；直接改 encoder@1 会破坏单位与旧算法；额外引入 ROS 消息依赖违背轻量跨平台目标。只采用熟悉形状和单位，不承诺 ROS 网络/消息二进制兼容。

## Consequences

Odometry 需要获授轮组标定；轮速来自实际运动，差速横滑仍不可观测。跨数组长度、名字注册、采样顺序和标定错误需要领域测试。未来轮电机/噪声/量化升级应显式描述模型，不改变本类型单位。

## Evidence / Acceptance Criteria

两底盘轮速反算和多文件 SDK 里程计均经 600 tick 探针，Schema 正例见 [joint-state-message.json](../examples/joint-state-message.json)，实现及限制见 [M1 报告](../reports/M1_VALIDATION.md)。此决定不引入 ROS2/DDS 运行时。

## 后续布局修订

[ADR-0019](0019-fourfold-omni-wheel-layout.md) 已按用户明确确认，将平行麦轮替换为四组 90° 旋转对称的固定普通全向轮；几何版本 radial_omni@1、R=0.25 m、r=0.10 m。本文的历史轮型/安装描述以新 ADR 为准；其他权限、单位、调度与模型边界继续有效。
