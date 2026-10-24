# ADR-0026 本机设置、模式授权与关卡存档

- Status: Accepted
- Date: 2026-10-24
- Scope: 本机原生/浏览器 Campaign 与开发者可视化；局部修订 ADR-0022 的自由选关/会话进度范围

## Context

用户要求设置页面与 YAML 键位映射，并区分按引导解锁的玩家模式和自由选关的开发者模式。开发者查看信息需像 RViz 一样独立开关图层，不能把真值混进玩家估计或扩大玩家代码权限。

## Decision

默认玩家模式，C0 → C1 → C2 用独立 JSON 存档记录通关。CLI 与 start API 共用解锁检查。原生只接受 Authority 的 passed 结果；浏览器由 Core Worker 的当前尝试 ticket 通知本机存储，保持单机信任范围。开发者练习不奖进度，模式切换撤销尝试并重建场景，退出后恢复玩家关卡。

默认 YAML 只作为首次种子，个人设置及存档放 `userdata/`，支持独立路径。键盘绑定、开发者开关和图层开关持久化；写入使用 CAS/文件锁/原子替换。PyYAML SafeLoader 拒绝对象标签、重复键和非法结构，依赖由现有启动器准备。

授权 PlayerViewSnapshot 保持原策略；开发者另走显式 grant 的只读 DeveloperSnapshot。UI 按图层自由显示真值、估计与当前传感器，但不会向玩家 Python 转发真值，也不修改 Selector 或 Core。玩家 C1/C2 仍通过算法生成地图目标，开发者才允许把 Radar 直接投影到地图调试。

## Alternatives

只在下拉框禁用关卡可绕过；只在前端隐藏真值违反既有权限边界。把真实位置发布到标准估计 Topic 会掩盖算法误差。将开发者通关写入玩家存档会绕开教学顺序。当前没有账号需求，暂不引入数据库/云同步或 ROS2/RViz 运行时。

## Consequences

新增本机管理 API 与文件格式，不修改玩家通信协议。单机设备所有者可开开发者或修改存档；浏览器完成通知不具备服务器验算证明，禁止将其用于 Arena 排行榜。其他标签页需要撤销旧 Worker；未保存草稿须先保存再切模式。存档升级、远程管理员身份与额外可视化消息类型需后续设计。

## Evidence / Acceptance

该交互和权限方向由用户明确要求；本机两种 Runtime 的实际改键、真实 C0 通关持久化、图层开关和退出开发者撤权见 [验收报告](../reports/SETTINGS_VALIDATION.md)。接口、文件结构、限制与验收条件见 [22](../22_SETTINGS_MODES_AND_PROGRESS.md)。接受范围不扩展到远程竞技或尚未实测的平台。
