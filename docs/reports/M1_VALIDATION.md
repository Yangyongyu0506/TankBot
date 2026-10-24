# M1 最小闭环验证报告

> 本文及 m1-baseline.json 为 M1 历史证据，保留原构建/配置摘要。当前 M1b 见 [新报告](M1B_VALIDATION.md)；旧测量工具重跑输出改为 m1-current-profile.json，不覆盖历史基线。


## 范围与复现

日期 2026-10-21。本轮按用户授权从设计阶段进入 M1；实现止于本机可信代码原型。根 AGENTS.md 保留原内容。构建/启动见 [根 README](../../README.md)，物理确认和取舍见 [13](../13_PHYSICS_MODEL_DECISIONS.md)、[ADR-0015](../adr/0015-confirmed-m1-physics-profile.md)。原始测量在 [m1-baseline.json](m1-baseline.json)，包含实际机器、配置/Cargo.lock/构建摘要、时延、误差、消息大小和 WASM 探针结果；重新测量会更新机器相关数值。

```bash
python3 tools/build.py
python3 tools/build.py --wasm
python3 tools/build.py --format-check
python3 -m unittest discover -s tests -v
python3 docs/tools/check_design.py
python3 tools/measure_m1.py
node tools/wasm_probe.mjs
```

本机未安装全局 Rust，使用仓库忽略目录下经 SHA256 核对的 Rust 1.99.1/rustfmt/native+WASM std；官方下载不可达，使用公开镜像，源码版本由 Cargo.lock 固定。工具链/依赖缓存不纳入交付，也不修改 shell 启动配置。正常开发机使用 rust-toolchain.toml 与常规 Cargo 即可。

## 实现与真实数据流

```mermaid
flowchart LR
  C[Rust Core / private truth] --> S[ideal joint_states + COM IMU]
  S --> H[Authority / input snapshot]
  H --> W[external CPython worker / multi-file odometry]
  W --> G[fixed commit gate / schema + grants + semantics]
  G --> P[candidate pose / PoseSelector]
  P --> T[/robot/localization/pose]
  T --> V[ViewGateway]
  V --> U[loopback HTTP / Canvas]
  K[keyboard Twist] --> H
  H --> C
```

Core 不引用 UI/网络/Python。Host 私有 IPC 可读取真值供仿真/测量，但 Runtime 初始化仅传公开起点、轮几何和算法配置；运行输入只有授权观测。UI 无 World/真值/配置 dump 入口；只画选中估计、静态公开地图和本地传感器。System Pose Provider 在 M1 禁用，配置启用会报错，不自动回退。

两底盘均为聚合刚体受力伺服，未模拟独立电机；4 子步重算力，接触共同求解法向/摩擦。理想编码器不等于完美定位：差速横滑、离散积分和碰撞位置修正仍可造成里程计差异。所有调参只在 `config/game.yaml`，公共 ControllerProfile 从中派生，不维护另一份控制数值。

## 验收证据

22 项单元/集成测试通过，其中 `tests/test_protocol_fixtures.py` 将 10 个已有文档领域负例接入真实校验器；`tests/test_m1.py` 验证真实原生 Core 与独立 Python 进程；不使用线程执行玩家算法冒充隔离：

- 两底盘 600 tick 传感器→Python→候选→标准位姿→Gateway；采样 30 Hz、激活 10 Hz；生成 tick 保留，通常 n+6 才提交。
- 力上限/伺服离散方程、独立转动惯量、目标截断、最新目标替换、差速拒绝 vy、主动制动与按生成时间超时。
- 墙体阻停/无编码器空转、偏心接触角动量、IMU 窗口平均；非弹性求解的穿透误差在公开容差内。
- 合法估计偏移 2 m 时画估计，真值不动；没有输出、错帧、非法协方差、异常时不回退真值；估计变旧后隐藏。
- 外部看门狗强杀真实死循环，600 tick 继续；Linux SIGSTOP 注入迟到，提交门后不补交。
- JSON 重复键/NaN/溢出、ACL/序号/run/时间/帧/PSD、SDK 不可变数据、文档 SDK 示例执行、缺参数拒绝、HTTP 真值路径 404 和控制跨源拒绝。
- 实际执行器输入重放到全新同构建 Core，逐 tick 位姿/速度完全相同；WASM 和原生均运行同一 600 tick 探针，本机结果相同，但这不是跨硬件位级一致保证。

原始基准为 debug 构建、单车/五墙；Host tick 包含 IPC、JSON/Schema 和受控测试等待，不是纯物理引擎基准。WASM 包含调试信息，不代表发布包体。实测误差和时间以 JSON 为准，不设虚假的通用 FPS 保证。

## 浏览器人工接口验证

本机 Firefox headless 通过 Marionette 加载完整页面，等待授权位姿后发送 W 按下/释放，估计 x 从 0.000 m 增加超过 0.10 m（末次复核为 0.107 m），页面显示轮速/IMU；截图保存在被忽略的 `.m1-cache/browser.png`。重跑前启动 M1 服务与临时 Firefox profile：

```bash
mkdir -p .m1-cache/firefox
firefox --headless --no-remote --marionette --profile "$PWD/.m1-cache/firefox" http://127.0.0.1:8765
```

在另一个终端运行 `python3 tools/browser_smoke.py`。该脚本需要已运行的 Firefox/Host，不属于默认单元测试依赖。Snap Firefox 的私有 /tmp 无法读取宿主临时 profile，所以使用仓库忽略目录。此验证运行的是原生 Core Host + Web UI，不是完整浏览器 WASM+Pyodide 部署。

## 限制与后续

只验证 Linux x86_64、Node WASM 与本机 Firefox。普通 Python 子进程没有文件/网络/内存安全沙箱；不接受第三方项目或联网竞技。Runtime 仅一个 periodic Module；SDK event、rng/log/state、手动 Topic、多模块调度未实现。Workspace 生命周期/模板/Edit-Test-Deploy 在 M3；炮台、弹丸、后坐力本轮只定模型。

M1 Replay 是有界私有短程执行器记录和测试注入，不是持久化 Replay 产品。WebSocket、平台 Adapter 等价性、完整浏览器双 Worker、Windows/macOS 和 OS 级沙箱继续按 M2/M8 验证。ADR-0002/0003/0013 保持 Proposed；本报告提供部分验证证据，不越过其完整接受门。下一具体任务见 [M2a](../10_DEVELOPMENT_ROADMAP.md)。
