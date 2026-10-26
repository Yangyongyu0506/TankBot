# 编辑器阶段锁定与 Space 发射验收

日期：2026-10-26。范围：本机 Firefox、原生 CPython 与浏览器 Pyodide；不改变关卡参数、机器人协议或 Authority 的部署语义。

## 原因与修复

旧编辑器关闭时把焦点恢复到此前的“代码编辑器”按钮；浏览器会将 Space 转为该按钮的原生点击，导致重新打开。现在关闭后始终聚焦游戏画布。

`web/workspace-dialog.js` 统一处理编辑入口和权威尝试状态。running 阶段关闭并锁定编辑器，包括顶部按钮、F2、F1、手柄 Start 和日志源码入口；算法异常不会解锁。准备阶段、启动失败、本局结束后均可编辑，重试创建新的准备阶段。部署状态可提前锁定，迟到的准备状态不会误解锁，终局后的旧 running 响应不会重新上锁。自由试验场继续允许编辑。该规则同时适用于玩家和开发者模式。

## 验证

| 检查 | 结果 |
| --- | --- |
| C2 成功部署自动关闭、焦点在画布 | 原生 / 浏览器通过 |
| 真实 WebDriver Space 单次输入增加 `shots_fired`，不打开编辑器 | 原生 / 浏览器通过 |
| 运行中 F2、F1、按钮及日志源码事件无法打开或聚焦隐藏编辑器 | 原生 / 浏览器通过 |
| 主动结束后 F2 可以打开，重试后恢复准备阶段编辑 | 原生 / 浏览器通过 |
| 累计 RMSE 仍更新，结束冻结，重试清零 | 原生 / 浏览器通过 |
| 手动开始、部署门、终局与迟到轮询 | Node 检查通过 |
| 键位映射与手柄输入规则 | 既有 Node 检查通过 |
| 运行异常后主动结束、日志跳转源码、修改、重试及重新部署 | 浏览器 Pyodide 通过 |

`tools/browser_live_metrics.py` 使用普通玩家模式和独立 Workspace/存档，不修改玩家代码。键盘使用可信 WebDriver Actions，包含浏览器原生默认行为。手柄入口由同一按钮门约束；实体手柄未在本轮重新测试。

本轮通过 14 项 Node 检查。记录及截图：`.m1-cache/editor-attempt-lock/{native,browser}-ui.json`、`runtime-feedback.json` 和对应截图。自动化入口：

```bash
node tests/test_workspace_dialog.mjs
node tests/test_settings.mjs
node tests/test_gamepad.mjs
python3 tools/browser_live_metrics.py --url http://127.0.0.1:8795 --port 2832 --output .m1-cache/editor-attempt-lock/native-ui.json
python3 tools/browser_live_metrics.py --url 'http://127.0.0.1:8795/?runtime=browser' --port 2832 --output .m1-cache/editor-attempt-lock/browser-ui.json
```

浏览器 QA 使用启用 `--browser-qa` 的独立服务与 Marionette Firefox；通过 `--prepare-store` 准备一次性 C2 解答与前置进度。未验证其他浏览器或操作系统。
