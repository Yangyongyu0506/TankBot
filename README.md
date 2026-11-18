# TankBot

TankBot 是面向机器人算法学习的二维编程游戏。玩家使用 Python/NumPy 实现感知、滤波、运动控制与导航；Rust/Rapier 负责权威物理，Python Authority 负责调度、权限和裁判，Godot 提供桌面显示与管理界面，VS Code编辑源码。

当前由 `assets/levels/*.yaml` 自动发现十三关：公共入门 C0、Weapons C1–C5、Navigation C0–C6。公共 C0 后同时开放两条主线，主线内按 YAML prerequisites 解锁，分别保留独立工程。

## 启动游戏

```bash
python3 main.py
# 已安装 uv 时也可使用：
uv run main.py
```

无需 `serve`、`browser` 或 `godot` 子命令；这些旧入口已移除。默认遵守玩家存档中的当前关卡和解锁条件。

`main.py`直接负责参数解析、依赖准备和启动流程；`tools/tankbot.py`已删除。两种启动命令共享同一依赖检查，不另建uv专用依赖清单。

首次启动自动准备 requirements.txt 中的 Python/NumPy 专用环境，以及固定版本和 SHA-512 的 Godot 便携包；不改系统 Python。Linux x86_64 支持自动准备 Godot，其他平台可指定 `--godot-binary /path/to/godot`，完整平台验证仍待完成。首次缺少 Core 时调用 Rust 构建，因此源码运行环境需要 Rust 1.99.1；当前尚无捆绑所有依赖的正式安装包。

```bash
python3 main.py --level c1
python3 main.py --level navigation.c0
python3 main.py --godot-binary /path/to/godot --offline
python3 main.py --list-maps
python3 main.py --level-tree
python3 main.py --level c0 --map open_large
```

锁定关卡不能通过CLI绕过。`--developer`或设置中开启开发者练习，可自由选关、独立查看真值与传感器，不计正式进度；地图覆盖同样只作练习，不解锁后续课程。地图资产预览界面仍待移植。

顶部“设置”或默认F10恢复键位映射、默认键位、玩家/开发者模式和图层选择；修改保存到`userdata/settings.yaml`，可用`--settings-file`隔离。运行中切换模式需先结束尝试，打开设置仍计时。“数据查看”列当前授权消息；开发者另可看真值、位姿候选和Runtime，关闭模式会清空私有显示，不扩大玩家程序权限。详见 [Godot设置与开发者显示](docs/44_GODOT_DESKTOP_CLIENT.md)。

## 用 VS Code 编辑，点击 Start 运行

安装 VS Code 并确保 `code` 在 PATH 中。F2/「VS Code」按钮打开当前章节真实代码目录和本关主要文件，在VS Code中编辑、新建文件并保存。Godot内置代码编辑器已删除，完整类型和算法说明仍在游戏「任务说明」中。

操作只需 **VS Code 保存 → 游戏点击 Start**。Start冻结版本，自动在独立CPython中完成原源码、依赖、合同、权限、项目测试和短输入检查，再启动全新正式Worker；规划课程仍执行独立检查与正式规划。失败直接显示Python日志，修正保存后再次Start。不需手动测试或部署，短测通过仍不等于正式通关。

运行中可在VS Code继续编辑，当前不可变运行版本不变；先「结束尝试」再Start才运行新代码。框架升级仍预览/明确确认，已有算法不覆盖。主界面日志显示 `print()`、Python异常及源码位置。任务栏更新保留滚动位置，切关/重试才回到顶部。

算法输入只包含课程授权的数据；估计不能修改真实物理状态。第三方库只开放NumPy及指定基础标准库，不提供任意pip安装。当前轮电压、里程计、GPS/EKF、航点、连续追踪、全局规划与局部避障课程的算法/评分合同保持，详见 [文档索引](docs/README.md)。

## 源码和存档

- `userdata/settings.yaml`：键盘映射、开发者模式和图层设置。
- `userdata/progress.json`：完成记录和当前关卡。
- `userdata/workspaces/<project>/files/`：VS Code编辑的真实文件，Ctrl+S后即保留在磁盘。
- 同级版本库：Start捕获的不可变revision、模板ledger、历史与归档；editable-recovery保留同步时移出的旧文件。

`--workspace` 是只读种子；`--workspace-store` 可指定版本库。验收或多项目运行可同时指定 `--settings-file`、`--save-file` 和 `--workspace-store`。跨关只补缺失文件；系统脚手架升级经预览/明确确认，不覆盖已有算法。重试重建运行状态，不删除源码。

磁盘和历史同改时冲突拒绝，两边保留。未Start的保存内容尚未进入revision备份，完整备份应包含整个userdata；VS Code未保存缓冲由编辑器管理。未找到VS Code时显示目录和安装/PATH提示，可在 `assets/config/desktop.yaml.editor.executable` 指定程序，arguments配置窗口选项。不自动安装扩展或覆盖已有.vscode设置，详见 [45](docs/45_EXTERNAL_EDITOR_AND_START.md)。

## 静态资源

游戏静态资源统一位于 [assets](assets/README.md)：`levels/`自动发现关卡，`templates/`保存各章节算法与系统适配器模板，`config/`保存模型及公共参数，`schemas/`定义消息/合同结构，`protocol/examples/`保存协议示例。地图与Sprite仍在`maps/`和`sprites/`。这些是生成工程的原始资源，玩家编辑的副本及历史始终存放在userdata，不能修改资源文件代替编辑自己的工程。

`protocol/`保留Python编解码、验证与Transport实现；实现代码不作为资源搬进assets。模板现已覆盖Weapons和Navigation；Hello Robot不要求算法，复用公共被动适配器。目录迁移、兼容边界和缓存策略见 [46](docs/46_STATIC_ASSETS_AND_ENTRYPOINT.md)。

## 构建与开发检查

日常构建、启动和标准检查不需要Node/npm，不加载浏览器或Pyodide。

```bash
python3 tools/build.py --offline
python3 tools/check.py --offline
python3 tools/check.py --suite python --offline
python3 tools/check.py --suite godot --offline -- --headless
python3 tools/check.py --suite godot --offline
```

Godot检查使用临时工作区、设置、存档、XDG目录和随机端口；窗口流程另保存截图，无头检查不证明实际显示或输入法。标准检查包含自动发现的Python回归、Rust、文档/Schema和生成配置一致性。含本地通信的测试需要允许loopback socket。

本轮X11环境的默认垂直同步窗口未完成握手；隔离诊断 `python3 tools/check.py --suite godot --offline -- --disable-vsync` 通过完整流程，生产显示设置未改。原因及证据见验收报告，不将诊断成功当作默认窗口可靠性保证。

保留以下开发能力，它们不提供浏览器GUI：

```bash
python3 main.py headless --level c0 --ticks 600
python3 main.py probe --level c0
python3 tools/build.py --wasm --release --offline
python3 tools/check.py --suite wasm
```

WASM对照需要Node和已构建的原生/WASM产物；仅此开发检查需要Node，无npm依赖。`tools/benchmark_runtime.py` 与校准工具只测原生后端，参数见 `assets/config/runtime-benchmark.yaml`；历史报告分析不启动已退役的浏览器Runtime。

## 当前边界和待移植界面

Web GUI、CodeMirror/npm构建、Pyodide/浏览器Workers及专用浏览器工具已删除。Godot仍通过本机HTTP管理API连接后端；这不是浏览器启动入口。

Godot提供Sprite、授权插值/相机、键鼠、VS Code入口、Start、升级预览、日志、设置/改键、开发者与导航图层、只读数据查看和关卡选择。以下功能仍待实现：

- 游戏专用交互矩阵实验；编辑器功能由外部VS Code及玩家自己的扩展提供。
- 控制/误差曲线、算法实验台。
- 工程导出、备份、历史恢复及清理管理面板；后端和数据仍保留。
- 手柄、完整关卡树及地图资产预览界面。

当前声明准入上限20ms、原生整批墙钟30ms，仍为experimental；固定6tick提交和规划准备预算不变。Godot显示不会自动消除Runtime截止或提交门故障。物理频率与渲染解耦，显示只消费View Policy授权数据。

本机CPython仅用于本人可信代码，普通子进程不构成强OS沙箱；服务器/Arena未上线。当前Godot证据限Linux，Windows/macOS构建CI不等同于完整玩家流程已验证。

设计与接口见 [44 Godot客户端](docs/44_GODOT_DESKTOP_CLIENT.md)、[ADR-0057](docs/adr/0057-godot-only-player-entry.md)；本轮证据见 [验收报告](docs/reports/GODOT_ONLY_ENTRY_VALIDATION.md)。旧Web/Pyodide报告保留为历史，不表示当前可运行。
