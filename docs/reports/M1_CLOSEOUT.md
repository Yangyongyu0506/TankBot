# M1 / M1b 收尾检查

## 范围与结论

2026-10-22 按路线图重新逐项检查。M1/M1b 功能范围已满足；本轮补齐了最新四轮径向全向底盘与武器组合的测量记录，并修正文档中的旧阶段/麦轮描述。完整编辑器、持久化 Replay、第三方代码沙箱属于后续里程碑，不作为 M1 隐含缺项。

根 AGENTS.md 按原要求保留；其“只有文档”的状态描述是历史基线，现状由根 README 和报告说明。

| 验收项 | 证据 |
| --- | --- |
| 差速/90° 旋转对称四全向轮；受力伺服、阻力、watchdog、接触和理想 Encoder/IMU | tests/test_m1.py、test_omni.py；13、ADR-0015/0019 |
| Physics→Sensor→Python→候选 Pose→Selector→Gateway→Web | 两底盘各 600 tick、98 次提交、无拒绝；[当前测量](m1-current-profile.json) |
| 错估计不改真值；无输出、错帧/PSD、迟到、卡死；不回退真值 | test_m1.py 的故障/隐私测试 |
| 双刚体炮台、幂等单发、冷却/寿命、反弹/自伤、弹丸互毁与冲量 | 10 项 Rust 测试、16 项 Python 武器测试；[当前武器测量](m1b-current-profile.json) |
| Python 武器接口、控制权与显式真值练习视图 | test_weapons.py；浏览器原型验收，M2 又复验同 SDK |
| 仿真/视图/rAF 分频、插值、固定世界朝向跟随相机、独立底盘模型 | 9 项 JS 测试、2 项 Python 渲染测试、[渲染报告](RENDERING_VALIDATION.md) |
| 原生/WASM 构建及同构建全部执行器重放 | 当前两份测量；tests/test_wasm.mjs 另对两底盘各 600 tick 全私有快照比较 |

## 当前证据与限制

本轮完整回归为 53 项 Python（原 M1/M1b 46 项，新增 M2 7 项）、10 项 Rust、9 项渲染 JS 和 WASM 双底盘集成对比。数值报告保留配置/Cargo.lock/二进制摘要、设备、时延分布、消息大小与冷启动；历史 m1-baseline.json、m1b-baseline.json、omni-baseline.json 不覆盖。

使用当前 5 m/s 弹速、独立炮台质量及既有数值近似。没有新增或改变用户尚未确认的物理模型；内部 1.4 仅增加浏览器配置。原生 CPython 仍只允许运行本人可信代码，没有 OS 安全沙箱。重放是有界私有验收录制，不是完整持久化产品。

M1 收尾后按用户授权实施 M2；交付与未验证平台见 [M2 报告](M2_VALIDATION.md)。
