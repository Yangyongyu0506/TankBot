# TankBot

TankBot 是面向机器人算法学习的二维编程游戏。玩家使用 Python/NumPy 实现感知、滤波、运动控制与导航；Rust/Rapier 负责权威物理，Python Authority 负责调度、权限和裁判，Godot 提供桌面显示与编辑界面。

当前由 `levels/*.yaml` 自动发现十三关：公共入门 C0、Weapons C1–C5、Navigation C0–C6。公共 C0 后同时开放两条主线，主线内按 YAML prerequisites 解锁，分别保留独立工程。

## 启动游戏

```bash
python3 tools/tankbot.py
```

无需 `serve`、`browser` 或 `godot` 子命令；这些旧入口已移除。默认遵守玩家存档中的当前关卡和解锁条件。

首次启动自动准备 requirements.txt 中的 Python/NumPy 专用环境，以及固定版本和 SHA-512 的 Godot 便携包；不改系统 Python。Linux x86_64 支持自动准备 Godot，其他平台可指定 `--godot-binary /path/to/godot`，完整平台验证仍待完成。首次缺少 Core 时调用 Rust 构建，因此源码运行环境需要 Rust 1.99.1；当前尚无捆绑所有依赖的正式安装包。

```bash
python3 tools/tankbot.py --level c1
python3 tools/tankbot.py --level navigation.c0
python3 tools/tankbot.py --godot-binary /path/to/godot --offline
python3 tools/tankbot.py --list-maps
python3 tools/tankbot.py --level-tree
python3 tools/tankbot.py --level c0 --map open_large
```

锁定关卡不能通过CLI绕过。`--developer` 明确开启开发者练习，不计正式进度；地图覆盖同样只作练习，不解锁后续课程。Godot完整开发者图层及地图预览界面仍待移植，开发者模式不表示这些界面已具备。

## 编辑和运行算法

F2 或顶部按钮打开全屏编辑器，×/同一快捷键收起。文件树高亮本关主要算法文件，支持多个 Python 文件、新建文件和 Ctrl/⌘S 保存。

执行顺序为保存 → 测试快照 → 部署已测试版本。测试在独立CPython中检查源码、依赖、合同、权限、项目测试和短输入；规划课程还执行独立规划检查。通过不等同于完整闭环通关。正式部署使用新Worker，Active后自动关闭编辑器；运行中须先结束尝试或重试再编辑。

主界面和编辑器日志提供 `print()`、Python异常及项目源码定位信息。右侧任务栏反馈更新保留滚动位置；切关/重试才回到顶部。

算法输入只包含课程授权的数据；估计不能修改真实物理状态。第三方库只开放NumPy及指定基础标准库，不提供任意pip安装。当前轮电压、里程计、GPS/EKF、航点、连续追踪、全局规划与局部避障课程的算法/评分合同保持，详见 [文档索引](docs/README.md)。

## 源码和存档

- `userdata/settings.yaml`：键盘映射、开发者模式和图层设置。
- `userdata/progress.json`：完成记录和当前关卡。
- `userdata/workspaces/`：完整源码、不可变revision、模板ledger、历史与归档。

`--workspace` 是只读种子；`--workspace-store` 可指定版本库。验收或多项目运行可同时指定 `--settings-file`、`--save-file` 和 `--workspace-store`。跨关只补缺失文件；系统脚手架升级经预览/明确确认，不覆盖已有算法。重试重建运行状态，不删除源码。

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
python3 tools/tankbot.py headless --level c0 --ticks 600
python3 tools/tankbot.py probe --level c0
python3 tools/build.py --wasm --release --offline
python3 tools/check.py --suite wasm
```

WASM对照需要Node和已构建的原生/WASM产物；仅此开发检查需要Node，无npm依赖。`tools/benchmark_runtime.py` 与校准工具只测原生后端，参数见 `config/runtime-benchmark.yaml`；历史报告分析不启动已退役的浏览器Runtime。

## 当前边界和待移植界面

Web GUI、CodeMirror/npm构建、Pyodide/浏览器Workers及专用浏览器工具已删除。Godot仍通过本机HTTP管理API连接后端；这不是浏览器启动入口。

Godot当前可完成授权绘图、插值/相机、键鼠、F2多文件编辑、升级预览、测试部署、日志和关卡选择。以下原Web界面尚未完成Godot移植：

- Vim、类型补全/悬停、交互矩阵实验。
- 控制/误差曲线、算法实验台。
- 工程导出、备份、历史恢复及清理管理面板；后端和数据仍保留。
- 设置/改键界面、手柄、完整关卡树。
- 完整开发者图层与各导航专用可视化。

当前声明准入上限20ms、原生整批墙钟30ms，仍为experimental；固定6tick提交和规划准备预算不变。Godot显示不会自动消除Runtime截止或提交门故障。物理频率与渲染解耦，显示只消费View Policy授权数据。

本机CPython仅用于本人可信代码，普通子进程不构成强OS沙箱；服务器/Arena未上线。当前Godot证据限Linux，Windows/macOS构建CI不等同于完整玩家流程已验证。

设计与接口见 [44 Godot客户端](docs/44_GODOT_DESKTOP_CLIENT.md)、[ADR-0057](docs/adr/0057-godot-only-player-entry.md)；本轮证据见 [验收报告](docs/reports/GODOT_ONLY_ENTRY_VALIDATION.md)。旧Web/Pyodide报告保留为历史，不表示当前可运行。
