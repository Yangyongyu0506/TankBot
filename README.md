# TankBot

TankBot 将二维坦克运动、机器人算法学习与多文件 Python 编程结合。玩家通过传感器和自己的算法重建世界认知。

当前完成 **M1 + M1b 本机闭环原型**：Rust/Rapier2D 权威物理、差速/四轮麦克纳姆底盘、理想轮编码器与质心 IMU、外部 Python 里程计、固定 tick 提交、Pose Selector、View Policy 和 Canvas 页面。M1b 增加双刚体炮台、单发/冷却、连续弹道/反弹/弹丸互毁、后坐/受击冲量、靶标与 Python 武器接口；尚无完整战斗关卡、编辑器或 Arena。

## 构建与运行

需要 Rust **1.99.1**、Python **3.10+**（本机实测 3.14.4）；WASM 探针另需 `wasm32-unknown-unknown` 和 Node。Python 依赖安装到自己的虚拟环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python3 tools/build.py
python3 tools/tankbot.py serve
```

打开 `http://127.0.0.1:8765`。差速：W/S 前后，A/D 转向。全向：W/S 前后，A/D 横移，Q/E 转向；启动时选择：

```bash
python3 tools/tankbot.py serve --chassis omnidirectional
python3 tools/tankbot.py serve --view weapons-practice
python3 tools/tankbot.py headless --ticks 600 --robot-demo
```

炮台 J/L 转动，空格或按钮单发（长按不连射）。默认估计视图隐藏真实弹丸，保留炮台与武器局部反馈；`--view weapons-practice` 明确授权显示真实车体、弹丸和靶标。Python 输入权限不增加。`--robot-demo` 使用独立的 [weapon_demo.py](examples/robot/weapon_demo.py) 控制炮台/开火，人工底盘仍可用；对应人工武器入口会拒绝。想观察程序控制可运行 `python3 tools/tankbot.py serve --robot-demo --view weapons-practice`。

所有可调模型、控制、场景及运行 profile 集中在 [config/m1.json](config/m1.json)，缺项报错，不补隐藏默认值。底盘只能在场景启动时选择。修改 Python 源码后重启创建新 run；M3 前没有编辑即部署、热更新或迁移功能。示例算法在 [examples/robot](examples/robot/localization/odometry.py)，支持多文件 import，启动不会改写源码。

`tools/build.py` 优先使用正常 Cargo；未安装时可使用本机已有的 `.tools/rust` 工具链与 `.tools/cargo` 缓存。这些目录被忽略，不是分发依赖。常规 Rust 环境也可直接 `cargo build --locked`。

## 验证

```bash
cargo test --locked
python3 -m unittest discover -s tests -v
python3 docs/tools/check_design.py
python3 tools/build.py --format-check
python3 tools/build.py --wasm
node tools/wasm_probe.mjs
python3 tools/measure_m1b.py
```

单元/集成测试包含临时 loopback HTTP 服务；受限环境需允许本地套接字。`measure_m1b.py` 更新私有武器评估基准 JSON，报告实际机器/摘要/时延/误差；不要把本机测量当成所有平台性能保证。运行说明与边界见 [M1b 验证报告](docs/reports/M1B_VALIDATION.md)，旧 [M1 报告](docs/reports/M1_VALIDATION.md) 与基线保留为历史证据。

## 当前边界与设计入口

本版仅运行**本人可信的本机 Python**；普通子进程不是安全沙箱，不能开放第三方代码上传。UI 仅接收 View Policy 授权的估计/传感器或显式练习图层，不提供通用真值接口；本机设备所有者仍可通过文件/调试器读取自己的数据。实测平台为 Linux x86_64；WASM 仅完成无头构建/执行探针，完整浏览器单机、Windows/macOS 和服务器隔离仍待验证。

从 [文档索引](docs/README.md)、[物理确认记录](docs/13_PHYSICS_MODEL_DECISIONS.md) 与 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 阅读。根 [AGENTS.md](AGENTS.md) 按用户要求保留原文件；其中“只有设计文档”的状态描述为历史基线，当前实现范围以本 README 和 M1b 报告为准，其架构约束继续有效。
