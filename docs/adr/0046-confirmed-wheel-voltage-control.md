# ADR-0046 用户确认的 Navigation 双轮电压控制

- Status: Accepted
- Date: 2026-11-02

## Context

用户要求首关由玩家实现差速 FK/IK、电机模型与实际速度指令执行。旧轮速只是车体反算，车体伺服已经代做控制。用户已逐项确认简化直流电机、轮参数、耦合/碰撞、时序与方形指令。

## Decision

保留 velocity_servo，增加仅用于无武器差速车的 wheel_voltage。i=(U−Keω)/R、τ=Kt·i，通过轮地反力与轮惯量等效耦合驱动车体，不写目标真实速度。数值取差速底盘 YAML；世界时钟/求解器独立。方程与接触近似见 [33](../33_NAVIGATION_MOTION_CONTROL.md)。

玩家输入 Twist、左右轮速 NumPy `(2,)` 和 dt，输出两轮电压 `(2,)`。框架校验形状、有限值与轮序，新增 wheel_voltage@1；旧消息不变。本关 cmd_vel 仅为系统参考输入，不能借此绕过电机。

采用 60 Hz/4 子步、30 Hz 编码器、10 Hz 玩家、6 tick 提交；零电压与 0.5 s 失联均电气制动。首批正式控制生效起算，24 s 序列结束当刻检查回原点≤0.30 m、真实路程≥7.2 m，重复部署不重置；不补未约定的制动等待。

## Alternatives

直接轮速隐藏电机控制，直接力矩略过电气模型；完整电感/电流与轮胎模型增加课程和数值负担，均未采用。把输出改交旧车体伺服会破坏学习目标，禁止。

## Consequences

可复用 Rust/WASM、传感器和 Module Runtime，Weapons 保持原驱动。轮惯量不参与瞬时接触求解，碰撞沿用原参数、轮速随后反算，不能宣称完整轮系接触动力学。双阈值不唯一约束路线，按需求保留并说明限制；更精细模型另行确认。

## Validation

Accepted 记录用户明确确认的模型/接口，不代表全平台支持。闭环、原生/WASM、网页和回归证据见 [验收报告](../reports/NAVIGATION_CONTROL_VALIDATION.md)。
