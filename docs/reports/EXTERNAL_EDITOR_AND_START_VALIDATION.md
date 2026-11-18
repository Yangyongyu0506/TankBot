# VS Code与单次Start验收

日期：2026-11-18。基线为`5e0f036`；本轮不提交/推送，不操作日常userdata。设计见 [45](../45_EXTERNAL_EDITOR_AND_START.md) 与 [ADR-0058](../adr/0058-external-editor-and-single-start.md)。

## 当前完成与证据边界

已实现真实编辑目录、基线/冲突保护、Start快照及自动检查/启动，删除Godot内置源码编辑与手动测试/部署操作；原检查器、Worker、权限、物理和关卡阈值保持。教学YAML仅修订编辑/运行操作文案，不更换算法目标和参数。

外部编辑/Start最终16项、桌面生命周期9项通过；新增检查包括并发保存、中断、显式升级与过期预览、相对/空格目录、缺失Manifest的错误恢复，以及Navigation C5独立规划后自动正式启动，未放宽5秒规划或20/30ms周期额度。

## Godot和VS Code实际流程

- 无头证据`.m1-cache/godot-qa/20261118T031459805014`：33项通过，使用记录型编辑器启动器，不声称打开真实编辑器。
- 真实窗口最终证据`.m1-cache/godot-qa/20261118T033342256310`：Godot 4.7.2、X11/OpenGL NVIDIA，VS Code 1.127.0独立user-data-dir/extensions-dir，禁用扩展；33项通过、两次外部打开请求，结束前隔离编辑器GUI进程仍存活，工具只关闭自己创建的进程。此前真实窗口成功记录`20261118T032010252548`也保留。
- 完成F2打开、真实代码文件落盘、错误源码Python日志、保存修正后单次Start自动检查/正式运行、授权估计进入视图、Space开火与C1实际通关。运行中修改磁盘文件不改变部署revision；重试捕获新保存，C0人工驾驶、Navigation/Weapons往返后原算法/自建文件/原revision/ledger均保留。
- 游戏无CodeEdit，只有只读说明/预览；默认无子命令/无关卡启动及窗口退出关闭后端的夹具也通过。测试驱动保存实际文件，不是通过人工VS Code键入；不宣称验收了输入法或Python扩展补全。

[机器可读摘要](external-editor-start-validation.json)、[游戏画面](assets/external-editor-start/game.png)、[只读说明](assets/external-editor-start/game-guide.png)仅含隔离测试内容。样本内无墙钟超时或错过提交门，不能据此提升experimental可靠性等级。真实窗口仍需测试参数disable-vsync，此前默认VSync握手失败的根因未在本轮修复。

## 命令与检查

| 命令 | 实际结果 |
| --- | --- |
| `.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_external_editor.py -v` | 最终16项通过，13.161秒 |
| 同入口 `test_desktop.py` | 9项通过 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 33项、默认启动/退出通过；记录型编辑器 |
| `python3 tools/check.py --suite godot --offline -- --disable-vsync --real-vscode --vscode-binary /usr/share/code/code` | 两次真实窗口流程通过，均33项 |
| `python3 tools/check.py --suite wasm` | 原生/WASM JSON ABI和既有课程/接触/武器等快照对照通过 |
| `python3 tools/export_profile.py --offline` | 更新生成夹具；课程改动仅操作文案 |
| `python3 tools/check.py --offline` | 最终重跑退出0：404项Python、18项Rust、文档/Schema/样例及生成配置一致性通过 |

首轮统一检查402项中4个冻结比对失败：仍逐字要求旧编辑/测试/部署文案。原始历史JSON、hash和报告没有改写；新增明确的22处教程文案变更夹具，仅在历史比对时还原这些字符串，其他物理、参数、权限、类型与课程规则仍严格比较。两项相关测试方法定向重跑通过，原失败日志保留于`.m1-cache/external-editor-qa/standard-check.log`。Schema初查因JSON排版非规范失败，规范化后文档检查通过。

## 文件与兼容

主要新增`external_editor.py`、`player_run.py`、16项外部编辑测试、22处文案比较夹具/辅助函数、45规范、ADR-0058及本报告。修改Godot main/integration、WorkspaceAPI/LocalServer、desktop配置/Schema、教程操作文案和生成夹具；README、AGENTS、索引及相关架构文档同步。

原源码/存档身份、robot Protocol、SDK、物理参数、评分阈值、准备与周期预算未更换。未Start的磁盘草稿不进入旧版本库导出，备份此类内容需保存整个userdata；游戏不会删除这些草稿。未保存缓冲由VS Code管理。没有安装扩展、上传代码、修改日常工程，未提交或推送Git。

所有验收采用临时设置、存档、Workspace、随机本机端口及隔离编辑器配置。Windows/macOS、其他编辑器、完整十三关GUI、扩展、长时磁盘恢复及长期可靠性未验收。历史报告和此前C6/VSync失败记录保留，不能因本轮工作流变化抹去。
