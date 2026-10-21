# TankBot

TankBot 将二维坦克运动、机器人算法学习与多文件 Python 编程结合。玩家通过传感器和自己的算法重建世界认知。

当前完成 **M1 本机最小闭环原型**：Rust/Rapier2D 权威物理、差速/四轮麦克纳姆底盘、理想轮编码器与质心 IMU、外部 Python 里程计、固定 tick 提交、Pose Selector、View Policy 和 Canvas 页面。炮台/弹丸/后坐力只完成模型约定，尚无战斗、关卡、编辑器或 Arena。

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
python3 tools/tankbot.py headless --ticks 600
```

所有可调模型、控制、场景及运行 profile 集中在 [config/m1.json](config/m1.json)，缺项报错，不补隐藏默认值。底盘只能在场景启动时选择。修改 Python 源码后重启创建新 run；M3 前没有编辑即部署、热更新或迁移功能。示例算法在 [examples/robot](examples/robot/localization/odometry.py)，支持多文件 import，启动不会改写源码。

`tools/build.py` 优先使用正常 Cargo；未安装时可使用本机已有的 `.tools/rust` 工具链与 `.tools/cargo` 缓存。这些目录被忽略，不是分发依赖。常规 Rust 环境也可直接 `cargo build --locked`。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 docs/tools/check_design.py
python3 tools/build.py --format-check
python3 tools/build.py --wasm
node tools/wasm_probe.mjs
python3 tools/measure_m1.py
```

单元/集成测试包含临时 loopback HTTP 服务；受限环境需允许本地套接字。`measure_m1.py` 更新私有评估基准 JSON，报告实际机器/摘要/时延/误差；不要把本机测量当成所有平台性能保证。运行说明与边界见 [M1 验证报告](docs/reports/M1_VALIDATION.md)。

## 当前边界与设计入口

本版仅运行**本人可信的本机 Python**；普通子进程不是安全沙箱，不能开放第三方代码上传。UI 仅接收授权估计和传感器，不提供真值接口；本机设备所有者仍可通过文件/调试器读取自己的数据。实测平台为 Linux x86_64；WASM 仅完成无头构建/执行探针，完整浏览器单机、Windows/macOS 和服务器隔离仍待验证。

从 [文档索引](docs/README.md)、[物理确认记录](docs/13_PHYSICS_MODEL_DECISIONS.md) 与 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 阅读。根 [AGENTS.md](AGENTS.md) 按用户要求保留原文件；其中“只有设计文档”的状态描述为历史基线，当前实现范围以本 README 和 M1 报告为准，其架构约束继续有效。
