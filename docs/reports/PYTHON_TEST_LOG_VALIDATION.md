# Python 测试与异常日志改进验收

## 范围与结果

2026-10-25，在 Linux x86_64 / Firefox 157.0.1 验证原生 CPython 与 WASM/Pyodide。玩家的 C2 KF 异常说明了通用 MODULE_ERROR 不能替代真实异常；本次保留机器错误码，并在游戏内显示 Python 详细错误。未修改玩家 Workspace、KF 算法、物理、Topic 或权限。

## 实现

- 项目单元测试用标准 unittest 详细输出，保留测试名称、print、全部失败调用栈及 Ran/OK/FAILED 汇总；随后输出授权传感器仿真各批次结果。
- 已由 unittest 打印的失败不再追加重复的框架异常栈；语法错误保留源码、行号、异常类型和 `^` 指示。
- Deployment 从对应任务/部署的有界 Python 输出提取 summary/path/line。保留原 error/runtime_fault 字段，增加可选 last.diagnostic 及可空 runtime_diagnostic；不改机器人协议。
- 编辑器测试时自动展开日志，失败摘要直接显示 Python 异常；调用栈连续显示，元数据按块显示，项目文件行可点击，提供复制原始日志。
- 日志继续使用现有字节/条数额度和版本身份，输出用文本节点显示，无额外真值访问。

## 自动化

完整 Python 回归 155 项通过；新增/扩展的日志专项覆盖 C2 NameError 的实际文件行号、全部 unittest 失败与 print、语法错误源码与指示、候选失败和运行异常、缓冲上限及 Worker 身份隔离。随后去重框架异常栈的专项 6 项也通过。Node 日志测试 3 项通过，覆盖跨 tick/分块连续拼接、版本/来源隔离和项目源码定位。文档、生成夹具和空白检查通过。

## 真实网页证据

[原生记录](python-test-logs-native.json)、[WASM/Pyodide 记录](python-test-logs-browser.json) 均完成：依赖拒绝→故意失败的项目单元测试→Python 原始失败日志与可定位摘要→修复测试→部署→运行异常调用栈→点击定位→来源筛选/清空→修复并重新部署。检查了 1280 和 500 宽度下页面不滚动、日志区域可见。截图路径记录在 JSON，图片位于忽略的 .m1-cache 目录。

测试使用独立端口、设置、存档和临时 Workspace，不操作用户游戏服务。原生记录对应日志改进的首个版本；浏览器记录和最终原生专项另验证了重复框架栈的清理。原始记录内的源码摘要描述其当次构建，不替代最终工作树的测试。

## 复现与限制

```bash
PYTHONPATH=sdk/python .m1-cache/learning-venv/bin/python -m unittest discover -s tests -v
node tests/test_runtime_logs.mjs
python3 tools/prepare_browser.py --offline
python3 docs/tools/check_design.py
```

真实 UI 使用 tools/browser_runtime_feedback.py：先对新目录执行 --prepare-store，再以独立服务和 Firefox 执行 --url、--browser-port、--output。需要已缓存的编辑器/Pyodide 与原生/WASM 构建。

日志仍有额度，极端输出可能被裁剪；Worker 被硬终止时不能保证产生 Python traceback。未实现断点、单步或交互变量检查，其他 OS/浏览器仍待验证。修改代码后需重新保存、测试并部署；旧快照日志不会随草稿改变。
