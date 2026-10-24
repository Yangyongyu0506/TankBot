# 学习说明与 SE(3) 练习验收

日期：2026-10-24。对应 [学习设计](../19_LEARNING_GUIDES_AND_SE3.md) 和 [ADR-0023](../adr/0023-typed-learning-and-se3-exercise.md)。本报告补充历史 [M4 验收](M4_VALIDATION.md)，后者记录的是调整 C1 接口之前的版本。

## 验证范围与环境

Linux x86_64；原生 CPython 3.14.4 / NumPy 2.3.3；Firefox 157.0.1 / Pyodide 0.29.5 / 锁定 NumPy 2.2.5。浏览器包摘要由 `config/browser-assets.lock.json` 校验。原生 NumPy 在专用虚拟环境安装，不依赖系统 Python 隐含的软件包。

本轮修改课程接口、模板、依赖和学习工具；没有调整已经确认的物理、噪声、武器或胜利规则。保留根 AGENTS.md 和此前 M4 原始报告。

## 数学、运行链与迁移

- C0–C2 均提供完成条件、操作步骤、调用与状态、常见问题；编程关卡附文件、完整签名、字段/单位和返回值说明。18 项类型参考从真实 SDK 声明及说明生成。
- 生成的 Python 参数、状态与变量显式注解，函数声明返回类型；AST 检查涵盖全部课程模板。公开 SDK 字段与参考内容一致。
- SE(3) 合成测试：自身 `(1,3,π/2)`，矩阵把 `[2,0,0,1]` 变为 `[1,5,0,1]`；方向 `[2,0,0,0]` 变为 `[0,2,0,0]`。逆变换恢复输入。
- 拒绝 list、错误形状、复数、非有限数、缩放、反射和错误最后一行。合法但错误的玩家矩阵在真实 Authority / Python 闭环中产生相应错误目标估计，未被真值纠正，真实车体与靶标位置保持独立。
- 旧教学 wrapper 提示预览升级。只采用系统脚手架可保留原 `coordinates.py`；原 revision 可恢复。新关仅补缺失文件，不覆盖既有算法。

原生完整回归 **80 项通过**；其中教学专项 6 项覆盖上述断言。补充运行 Node SDK 提示及渲染测试通过，文档检查与 `git diff --check` 通过。实际使用的原生命令：

```bash
.m1-cache/learning-venv/bin/python -m unittest discover -s tests -v
.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_learning.py -v
node --test tests/test_sdk_hints.mjs tests/test_rendering.mjs
python3 tools/build.py --web-only --offline
python3 tools/prepare_browser.py --offline
python3 docs/tools/check_design.py
```

## 真实浏览器流程

证据：[learning-browser.json](learning-browser.json)，包含当前源码、锁文件、JS/Python bundle、原生 Core 与 WASM 摘要。

```bash
python3 tools/tankbot.py browser --level c0 --browser-qa --workspace-store .m1-cache/learning-browser-v3
# 使用启用 Marionette 的 Firefox 后执行：
python3 tools/browser_m4.py --learning --output docs/reports/learning-browser.json
```

检查逐关说明、F1 打开/收起、Pose2D 类型/单位、固定签名、Ctrl+Space 成员提示、矩阵逐行乘法、点/方向切换及窄窗口辅助面板。深色主题的文档字符串显示为 `rgb(184,217,155)`，避免暗红文字难以阅读。编辑区和参考区独立滚动，网页不滚动。

流程通过 C0 驾驶/射击 → C1 在编辑器填写 NumPy 矩阵、Test/Deploy 后命中 → C2 保留矩阵文件、填写跟踪类并击杀 3 HP 敌车。每关有新 run_id，C1/C2 View 未出现隐藏真值对象。

截图输出在 `.m1-cache/learning-browser-types.png`、`learning-browser-matrix.png`、`learning-browser-matrix-product.png`、`learning-browser-tracking.png`，不提交本机生成缓存。

## 证据边界

这验证已有原生/Firefox 本机 profile，不扩展为其他操作系统、浏览器或 Arena 的通过声明。类型提示是显式注解与课程参数的轻量辅助，尚非完整 Python 语言服务器；矩阵实验使用独立合成数据，未连接隐藏真值。二维物理继续通过 z=0 嵌入 SE(3)，不表示已实现三维动力学。
