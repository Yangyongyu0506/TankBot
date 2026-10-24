# 关卡计时、玩家生命与 YAML 参数验收

日期：2026-10-25。环境：本机 Linux、原生 CPython、Firefox 157.0.1 / Pyodide 0.29.5。范围与保证边界见 [25](../25_ATTEMPT_RULES_AND_CONFIGURATION.md)。本轮不改变已确认的运动/弹丸/冲量模型，不增加敌车开火 AI。

## 自动化规则检查

完整 Python 回归 **116 项通过**；Rust **15 项通过**。Node 渲染、SDK 提示、手柄和设置检查通过；同工具链原生/WASM 的 2×600 武器及 1800 Campaign 快照一致，JSON ABI 负例和缓冲边界通过。文档、Schema、YAML/生成夹具一致性和 Rust 格式检查通过。

`tests/test_attempt_rules.py` 验证 YAML 与生成夹具相同、重复键/对象标签/非有限数值/循环与非 JSON 值拒绝；准备与测试不计时、零输入不起算、正式部署起算、重复部署保留开始 tick；准确截止、最后 tick 可通关、同时死亡优先失败、主动结束及真实反弹弹丸导致 3→2→1→0 HP。死亡后视图不保留车体或旧观测，控制拒绝，报告固定。

Rust `player_health_tests` 在两种底盘上验证真实接触伤害、非致命冲量、不增质量、致命移除双刚体、死亡后拒绝控制与开火、弹丸穿过已移除位置且不产生新受击；未配置 HP 的 C0/C1/沙盒仍只累计命中。

运行命令：

```bash
python3 tools/export_profile.py --offline
cargo test --locked
python3 -m unittest discover -s tests -v
node tests/test_wasm.mjs
node --test tests/test_rendering.mjs tests/test_sdk_hints.mjs tests/test_gamepad.mjs tests/test_settings.mjs
python3 docs/tools/check_design.py
```

## UI 场景与复现

使用独立端口 8785/8786、Marionette 2831，以及独立 YAML/settings/save/workspace；未操作日常玩家项目。`tools/browser_attempt_rules.py --prepare <新目录>` 从正式 YAML 派生测试场景：仅将时限缩短为 2/8/30 秒并用反弹墙验证自伤；正式值仍为 60/60/120 秒。准备工具拒绝覆盖已有目录。

启动示例（先构建原生/WASM 并准备浏览器资源）：

```bash
python3 tools/browser_attempt_rules.py --prepare .m1-cache/attempt-example
python3 tools/tankbot.py serve --config .m1-cache/attempt-example/config.yaml --level c0 --developer --workspace-store .m1-cache/attempt-example/workspace --settings-file .m1-cache/attempt-example/settings.yaml --save-file .m1-cache/attempt-example/progress.json
python3 tools/browser_attempt_rules.py --url http://127.0.0.1:8785 --output docs/reports/attempt-rules-native.json
```

浏览器模式用另一个新目录，将 `serve` 换为 `browser --browser-qa`，URL 加 `?runtime=browser`，输出到 `attempt-rules-browser.json`。[原生 UI 记录](attempt-rules-native.json) 与 [浏览器 UI 记录](attempt-rules-browser.json) 均通过。脚本实际调用测试/部署、编辑器结束按钮、重试和开火；记录倒计时、玩家死亡、双方 HP、源码摘要、截图及固定视口。它会故意让测试程序失败，不能指向日常项目。

## 限制

短场景不代表完成默认 120 秒的教学难度评估、长期资源测量或全部 OS/浏览器认证。仿真时钟受设备调度/后台节流影响，不能当作 Arena 墙钟；当前敌车不主动射击。历史报告的旧计数与摘要仍对应当时构建。
