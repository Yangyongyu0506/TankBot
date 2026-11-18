# Godot界面对比度与布局验收

日期：2026-11-18；基线提交`782cc4a`。本轮仅调整桌面外观及对应配置/验证，不修改物理、课程、协议、运行预算或玩家源码。未提交/推送Git，未操作日常userdata。

## 完成范围

保留深色场景，普通按钮改为浅色实心、Start青色、结束尝试红色。悬停、按下与禁用均有独立样式。主工具栏、状态、场景、任务和日志通过边框、留白及字体层次分区；图层按钮同时显示开关文字和颜色，滚动条更清楚。

主题由`config/desktop-theme.yaml`统一配置，经Schema验证后只进入Godot。`clients/godot/ui_theme.gd`负责生成Theme，`main.gd`复用主题和面板；旧desktop配置省略theme_file时使用同一默认文件。未改变VS Code保存、Start自动检查/快照/运行及既有输入规则。

按sRGB相对亮度计算，普通/Start/停止按钮全部状态（含禁用）的文字对比度最小约4.62:1，填充对相邻面板最小约5.82:1；高于本主题4.5:1和3:1目标。测试也检查正文及次级文字对各暗色面板的对比度。这不等于完整无障碍认证。

## 实际执行

| 命令 | 结果与范围 |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_desktop.py -v` | 12项通过：启动清理、配置兼容、主题验证与各状态对比度 |
| `.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_external_editor.py -v` | 16项通过，13.342秒：源码冲突保护、升级、历史、Start及独立规划 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 首版33项既有流程通过，证据`20261118T104405163798`；当时尚未加入主题专项断言 |
| `python3 tools/check.py --suite godot --offline -- --disable-vsync` | 首轮56项、最终57项通过；最终证据`.m1-cache/godot-qa/20261118T104624880479` |
| `python3 docs/tools/check_design.py` | 文档、链接、Schema、样例及代码片段检查通过 |
| `python3 tools/export_profile.py --check --offline` | 生成配置一致；未修改Core夹具 |
| `git diff --check` | 通过 |

真实窗口使用Godot 4.7.2、Linux X11/OpenGL、NVIDIA RTX 5070 Laptop GPU，1440×900。验证了主题实际解析、按钮位于视口内、开关文字/状态、滚动保持、Python错误日志、F2、保存后Start、授权估计渲染、Space开火及C1通关；重试、C0驾驶和Navigation/Weapons往返后源码/revision/ledger保留。关闭客户端后后端清理通过。

所有流程使用临时配置、进度、Workspace、XDG目录与随机本机端口。编辑器启动器为记录夹具，测试写入真实代码文件；本轮没有启动真实VS Code或声称验证了人工输入。保留此前真实编辑器验收，见 [外部编辑与Start](EXTERNAL_EDITOR_AND_START_VALIDATION.md)。

## 截图

- [可用按钮与任务面板](assets/godot-ui-contrast/game-ready.png)
- [Start悬停](assets/godot-ui-contrast/game-hover.png)
- [运行中与禁用按钮](assets/godot-ui-contrast/game.png)
- [只读任务说明](assets/godot-ui-contrast/game-guide.png)

## 失败记录与限制

首次沙箱内Godot测试因禁止本机套接字而无法启动；获准在沙箱外、仍使用隔离数据后通过。外部编辑测试首次误用无NumPy的系统Python，导入失败；改用项目已准备环境后16项通过。日志保留在`.m1-cache/ui-theme-qa/`，未删去失败记录。

窗口回归继续使用已有`--disable-vsync`测试选项；此前默认VSync握手问题没有在本轮修复，生产显示配置未改变。未验证其他分辨率、Windows/macOS、完整十三关GUI或全部开发者图层；未重跑无关物理基准、WASM或全套标准回归。原生30ms profile仍为experimental。

## 文件

新增`config/desktop-theme.yaml`、`clients/godot/ui_theme.gd`、`docs/schemas/desktop-theme.schema.json`及本报告/截图。修改`config/desktop.yaml`及Schema、`host/tankbot_host/desktop.py`、`clients/godot/main.gd`、Godot集成回归、`tests/test_desktop.py`、文档检查器、44规范和文档/Schema索引。没有修改课程定义、玩家工程或历史报告。
