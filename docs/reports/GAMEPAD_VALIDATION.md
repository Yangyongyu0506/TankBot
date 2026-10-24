# 手柄输入验收

日期：2026-10-24。对应 [20 手柄驱动](../20_GAMEPAD_INPUT.md) 和 [ADR-0024](../adr/0024-gamepad-manual-input.md)。

## 环境与证据边界

Linux x86_64、Firefox 157.0.1、原生 CPython 3.14.4，以及现有 Rust/WASM + Pyodide 浏览器 Runtime。输入通过 WebDriver 在页面中模拟 `navigator.getGamepads()` 的标准样本，实际执行生产 RAF、UI 仲裁、人工请求、Authority 和物理引擎；没有替换生产输入模块或直接写入物理状态。

这是**软件链路验收**，未连接实体手柄，不认证 Xbox、DualSense、Switch、通用摇杆、Steam Input 或其他操作系统/浏览器组合。实体设备识别及 USB/蓝牙差异仍需后续硬件验证。页面继续使用现有权限裁剪；测试显式选择已有真值练习视图读取自身运动，没有新增真值接口。

| 实际闭环 | 证据 |
| --- | --- |
| 原生 Host + 差速底盘 | [gamepad-native.json](gamepad-native.json) |
| 浏览器 WASM + 全向底盘 | [gamepad-browser.json](gamepad-browser.json) |

JSON 记录实际位移、转向/炮台角变化、断连停车、单发、编辑隔离、失焦处理和源码摘要。该表不是四种组合全部独立验收的声明；纯输入测试另覆盖两种底盘的映射规则。

## 检查结果

- **82 项 Python 回归通过**，其中新配置测试检查完整/非法手柄配置、旧配置无 gamepad 时仍兼容，以及 robot 租约拒绝人工底盘/炮台/开火。
- **19 项 JavaScript 测试通过**：7 项手柄、10 项渲染、2 项类型提示。手柄测试包含径向死区、模拟幅度、斜推限幅、差速 vy=0、自定义索引/符号、单发边沿、多个稀疏设备、设备替换、停用/重连回中、错误样本、编辑隔离及键盘逐执行器优先。
- 两条真实网页闭环均验证前进、差速转向或全向横移、炮台旋转和 RT 单发；超过冷却时间长按扳机仍只有一发。
- 编辑器打开时推杆/按扳机没有移动或射击；Start 可收起，收起后保持推杆/扳机不会自动恢复。断连提交零目标，轮速降低后位置保持稳定；重连必须回中。
- 模拟 blur 事件触发现有窗口处理器并要求回中；Gamepad API 抛错时仍能键盘驾驶。隐藏页面的许可状态也由纯状态测试覆盖，不将合成 blur 当作实体设备或系统后台行为认证。
- 原有 `browser_dialog.py` 的 F2/按钮/×、焦点、草稿保留、键盘隔离及多窗口尺寸回归通过。手柄页面在实际 1280 px 与 500 px 宽度无网页滚动；本机 Firefox 将更窄请求限制为 500 px，没有据此声称验证 360 px。
- 文档检查、Schema 与 `git diff --check` 通过。根 AGENTS.md 保持原样。

截图在 `.m1-cache/gamepad-native.png`、`.m1-cache/gamepad-browser.png`；弹窗回归输出 `.m1-cache/dialog-report.json`，不提交本机生成缓存。

## 复现

使用装有 requirements.txt 依赖的 Python 环境；可用既有原生/WASM 构建，浏览器模式先运行 prepare 工具。

```bash
python3 -m unittest discover -s tests -v
node tests/test_gamepad.mjs
node tests/test_rendering.mjs
node tests/test_sdk_hints.mjs
python3 tools/prepare_browser.py --offline
python3 docs/tools/check_design.py
```

开启带 Marionette 的本机 Firefox，分别启动下列服务；两种服务占用相同端口，不能同时运行。测试会通过模拟输入移动和开火，只使用专用临时 Workspace。

```bash
python3 tools/tankbot.py serve --view weapons-practice --workspace-store .m1-cache/joy-native-final
python3 tools/browser_gamepad.py --output docs/reports/gamepad-native.json

python3 tools/tankbot.py browser --chassis omnidirectional --view weapons-practice --browser-qa --workspace-store .m1-cache/joy-browser
python3 tools/browser_gamepad.py --url 'http://127.0.0.1:8765/?runtime=browser' --output docs/reports/gamepad-browser.json
python3 tools/browser_dialog.py --url 'http://127.0.0.1:8765/?runtime=browser'
```

## 后续硬件验收

逐设备记录操作系统、浏览器版本、USB/蓝牙方式、浏览器 mapping、轴与按钮索引；实测首次唤醒、热插拔、后台/恢复、低电量断连及多设备选择。标准映射正确后复核左/右方向、幅度、扳机阈值和编辑隔离；若浏览器不给 standard 映射，按配置明确校准，不能凭设备名称自动猜测。
