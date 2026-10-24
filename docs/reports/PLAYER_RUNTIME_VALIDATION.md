# 玩家依赖、NumPy 与运行反馈验收

日期：2026-10-25；环境：本机 Linux / CPython 与 Firefox 157.0.1 / Pyodide 0.29.5。范围为 [23](../23_PLAYER_CODE_AND_LIBRARIES.md)、[24](../24_RUNTIME_LOGS.md)，不修改物理参数。

## 验证内容

- 完整 Python 回归 111 项通过；另通过 SDK 提示及渲染 Node 测试与文档/Schema 检查。此计数对应本轮构建，不替代历史平台性能报告。
- Python 回归覆盖课程静态导入、测试目录、未调用函数、动态导入、预加载外部包、相对 import、矩阵形状/只读/旧构造与 JSON 往返；新增跨关测试逐字节验证全部文件而非仅算法文件。
- C2 坐标数组重复创建 10000 次，每个当前批次的数组至多 16 字节；这是当前 0/1 检测的数组大小断言，不是完整 Python/浏览器长期 RSS 测量。
- 日志单测覆盖 UTF-8 字节上限、旧记录裁剪、原生 setup/print/traceback、候选初始化失败、浏览器 worker 身份隔离。
- [原生 UI](runtime-feedback-native.json) 与 [浏览器 UI](runtime-feedback-browser.json)：真实 CodeMirror 编辑禁止库并看到明确拒绝；修改为 NumPy 算法后 Test Ready、Deploy；运行后制造 ValueError，日志显示异常并能点击定位；筛选测试来源、清空显示、修复后重新部署恢复输出。
- 两种 UI 均通过第三个项目单元测试验证 `(2,2)` 只读协方差和 `(0,2)` 空测量数组；正式发布的协方差仍是 `[1,0,0,1]`。测试报告为 3 项 unittest 和 6 批授权传感器试运行。
- 编辑器与 HUD 都显示日志；1280、500 像素窗口下无网页滚动，日志区保留内部滚动空间。截图路径和源码摘要记录在 JSON。

原始测试只使用独立端口 8785/8786、Marionette 2831 以及独立 settings/save/workspace，未修改日常玩家源码或进度。其他 OS/浏览器、内存攻击、日志洪泛 CPU 压力和长期磁盘回收不在此报告的完成声明中。

## 复现

```bash
python3 -m unittest discover -s tests -v
node tests/test_sdk_hints.mjs
node tests/test_rendering.mjs
python3 docs/tools/check_design.py
python3 tools/prepare_browser.py --offline
```

先用具备 requirements 的解释器为每种模式创建全新测试库：

```bash
python3 tools/browser_runtime_feedback.py --prepare-store .m1-cache/feedback-project
```

复制仿真配置，仅将 host/runtime 端口改为 8785/8786，启动 `serve` 或 `browser`（后者带 `--browser-qa`），指定 `--level c1 --developer --workspace-store <该测试库>` 及独立 `--settings-file` / `--save-file`。启用 Marionette 2831 的独立 Firefox 后运行：

```bash
python3 tools/browser_runtime_feedback.py --url http://127.0.0.1:8785 --output docs/reports/runtime-feedback-native.json
python3 tools/browser_runtime_feedback.py --url 'http://127.0.0.1:8785/?runtime=browser' --output docs/reports/runtime-feedback-browser.json
```

脚本会编辑、测试、部署并故意使程序出错，不能指向日常项目。两种模式使用不同的新库；准备工具拒绝覆盖已有 HEAD。

## 保证边界

不支持任意第三方包安装；教学白名单不等于强 Python 沙箱或代码原创证明。数学矩阵用 NumPy；对象集合仍保持已有接口。日志只取玩家 Runtime，来源/版本由 Authority 标注；接收 tick 不是精确的打印采样时间。没有断点/单步 debugger，旧草稿行号与运行版本可能不同。
