# ADR-0024 手柄输入适配与人工控制租约

- Status: Accepted
- Date: 2026-10-24
- Scope: UI 输入、人工控制仲裁、设备生命周期

## Context

用户要求手柄驾驶及普通游戏的即插即用体验。当前两种 Runtime 共用人工控制接口，配置枚举 keyboard/robot，连续执行器已有 Twist、TurretVelocity、watchdog；不能让新设备绕过这些边界。

## Decision

在 Web UI 使用 Gamepad API，每 RAF 采样，按配置周期发送已有人工接口。将既有 keyboard 枚举解释为 UI 人工租约，涵盖键盘、屏幕和手柄；保留枚举与 API 兼容。逐执行器使用键盘优先仲裁，不叠加不同设备的速度。程序接管后手柄不获得额外权限。

默认标准布局，支持配置自定义索引与方向，参数保存在 config/m1.json。采用死区、单发按下边沿、设备选择、零目标和回中后重新接管。编辑器屏蔽执行器输入，Start 仍可收起；失焦/断连/重连不会补发旧输入。详见 [20](../20_GAMEPAD_INPUT.md)。

## Alternatives

原生 HID/SDL/Steam Input 服务增加安装及平台适配，不利于当前共享网页。新增 gamepad 控制源租约会让键盘与手柄切换污染 Authority 权限模型。持续发送原始 Joy 到玩家 Runtime 增加不需要的协议与教学负担；不同人工输入直接相加会造成限速与停止语义不清。

## Consequences

依赖浏览器识别设备与安全上下文，非标准设备需要显式映射；不保证所有硬件即插即用。保留同一权威、Topic 与制动语义，无物理模型变更或 ROS2/DDS 依赖。UI 软件验收和实体设备兼容性必须分别记录。

## Acceptance

2026-10-24：82 项 Python 回归、19 项 JavaScript 测试、原生差速与 WASM 全向网页闭环、编辑/断连/失焦边界及弹窗回归通过，见 [手柄验收](../reports/GAMEPAD_VALIDATION.md)。接受输入适配与仲裁设计；设备样本为模拟 Gamepad API，实体手柄和其他平台兼容性仍待硬件验证。
