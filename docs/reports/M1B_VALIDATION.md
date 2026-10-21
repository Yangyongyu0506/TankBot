# M1b 最小武器闭环验证报告

## 范围与复现

验证日期：2026-10-21 至 2026-10-22（Asia/Shanghai）。已按用户逐项确认实现 [14](../14_WEAPONS_DESIGN.md) / [ADR-0017](../adr/0017-confirmed-weapons-loop.md)，保留根 AGENTS.md 与玩家现有定位源码。本轮止于 M1b，不自动开展 M2a。

```bash
python3 tools/build.py
cargo test --locked
python3 -m unittest discover -s tests -v
python3 docs/tools/check_design.py
python3 tools/build.py --format-check
python3 tools/build.py --wasm
node tools/wasm_probe.mjs
python3 tools/measure_m1b.py
python3 tools/tankbot.py serve --view weapons-practice
python3 tools/tankbot.py serve --robot-demo --view weapons-practice
```

依赖及工具链入口见 [根 README](../../README.md)。本机使用已缓存 Rust 1.99.1、Rapier2D-f64 0.36.1、Python 3.14.4；未新增依赖。`--offline` 可用于已有完整 Cargo 缓存的构建。Python 测试含临时 loopback HTTP 服务，需要本地套接字权限。

## 已验收行为

- 双刚体中心炮台，独立质量/惯量、反向力矩、连续相对角、主动制动和 0.5 s watchdog；真实负载改变底盘响应。
- 发射前炮口世界速度继承、相对动量后坐；受击世界动量；差速投影 x、全向保留方向，底盘保留偏心角冲量，命中不加质量。
- 整段炮管阻塞拒绝；冷却第 15 tick 边界、拒绝/重复不延长冷却；开火日志有界且不淘汰旧 ID。
- 连续静态/旋转车体查询、弹丸对扫掠、多弹同刻互毁图、坦克/靶标优先级、墙角逐面计数、第四次墙接触销毁、半开寿命、同子步离膛反弹自伤。
- 专用 Topic/Command、类型化 SDK、真实外部 Python 调用与 n+6 门、按执行器的控制源与身份/帧/时间校验、非法输出整批拒绝。
- 默认视图与私有武器真值无关；练习模式经系统源/Selector/Gateway 授权，Python 仍只接收传感器和自身武器状态。旧 view_snapshot@1 不能夹带实体。
- 两底盘各 600 tick 的程序炮台/开火闭环与全执行器重放；原 M1 裸底盘回归明确关闭武器，不把额外 2 kg 偷算进旧模型。

**38 项 Python 测试、10 项 Rust 测试全部通过**；文档工具另验证 22 个正例与 25 个结构负例。当前测试入口：[Rust 事件/冲量测试](../../core/src/cannon.rs)、[M1b 集成测试](../../tests/test_weapons.py)、[M1 回归](../../tests/test_m1.py)。文档中的武器 SDK 片段也真正执行，结构负例覆盖命令关联、帧、空 payload、反馈脱敏和 @1 实体限制。

## 数值与平台证据

原始测量见 [m1b-baseline.json](m1b-baseline.json)，含本次 Core/配置/锁文件/WASM 摘要及实际时延，重跑更新测量值。固定子步 1/240 s；受击延迟上界为一个子步，不声称连续精确冲量耦合。默认单发首面墙扫掠时间与解析值绝对误差为 0 s，弹速镜面反射误差为 0 m/s（本机该夹具的 f64 结果）。内部受击测试对两底盘线冲量及偏心角冲量作数值断言；不是仅检查“坦克被推动”。

原生与 Node WASM 执行相同 600 tick 武器探针，均发射 34 发，炮台累计相对角 19.325407628508533 rad，本机精确相等。真实 Python 固定延迟示例有 32 次发射，两底盘均无输出拒绝，全量执行器重放结果与原运行相同。两种结果的输入时序不同，不应相互当作误差。

本机 Linux x86_64、debug 构建；WASM 带调试信息约 60.5 MB，不能代表生产包体。Host tick 包含 IPC/JSON/Schema/受控测试等待；时延分布以 JSON 为准，不外推全平台 FPS 或位级确定性。

## 浏览器验收

使用真实无头 Firefox/Marionette 分别启动默认估计视图与显式真值练习视图，执行前进、J 键旋转、空格单发和多次 repeat keydown；两模式均只增加一发，状态/视图标识正确。工具为 [browser_smoke.py](../../tools/browser_smoke.py)，连接已启动的服务与 Marionette：

```bash
python3 tools/browser_smoke.py --weapons --screenshot .m1-cache/m1b-estimated.png
```

截图存于被忽略的本机 `.m1-cache/`，不作为构建依赖。该浏览器访问原生 Authority；完整浏览器 WASM + Pyodide 双 Worker 尚未实现。权限裁剪由 Authority 完成，不能把页面截图代替协议泄漏测试。

## 限制与下一任务

受击后当前子步不回滚，车体轨迹采用首尾插值；微米级分离、固定弹药质量和差速横向冲量丢弃均为明确近似。还没有多动态坦克、伤害/死亡、连射、敌人、声音、热切换控制源、编辑器/部署 UI 或 Arena。

CPython 子进程仍非安全沙箱，仅允许本人可信本机代码；未声称 Windows/macOS、完整浏览器部署或远程服务已验证。技术 ADR-0002/0003/0013 保持 Proposed。下一开发任务是路线图 M2a 浏览器双 Worker 探针，本轮不开始。
