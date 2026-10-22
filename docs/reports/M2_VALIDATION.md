# M2 本机浏览器与 Adapter 验收

## 结论与范围

2026-10-22，M1/M1b [收尾复核](M1_CLOSEOUT.md) 后，已完成 M2 的浏览器双 Worker、实际 WASM init/step、多 Adapter 等价与资源测量。Linux x86_64 / Firefox **157.0.1** 实测通过；其他 OS/浏览器仍待执行。这里只接受已测本地 profile，未交付服务端沙箱、编辑器或 Arena。

物理与控制参数沿用用户确认配置，弹速仍为当前文件的 5 m/s；内部版本 1.4 仅新增 browser 配置。根 AGENTS.md 和玩家 Workspace 没有被覆盖。

## 实际交付

| 交付 | 实现/证据 |
| --- | --- |
| 共用私有 Core DTO 与显式 WASM ABI | core/src/session.rs、wasm.rs、web/wasm-core.js；原生/WASM 两底盘各 600 tick 全快照比较，含炮台/发射/弹道 |
| 共用 Authority / ModuleRunner | core_factory/worker_factory 注入；可信 Worker 内 Pyodide Authority→Rust；另一 Pyodide Worker 跑同一多文件里程计/武器 SDK |
| 真实浏览器闭环 | [全向](m2-browser.json)、[差速](m2-browser-differential.json)，每次 600 tick、98 次位姿提交、无拒绝，提交延迟均为 6 tick |
| 期限终止与恢复 | [故障](m2-browser-fault.json)：死循环在提交门 tick 12 被拒绝，tick 继续到 600；后续重新加载正常部署生成独立 run 并恢复提交 |
| 程序武器 | [武器](m2-browser-weapons.json)：同一 Python WeaponDemo 控制炮台并发射 27 发，零批次拒绝 |
| Transport | 49 个 Envelope 夹具：17 正例、22 结构负例、10 领域负例；真实 IPC/WebSocket、Memory/Replay 和浏览器 MessagePort 回送后进入同一 Validator，判定一致 |
| 界面与插值 | 90 个实际显示帧中 42 对同快照序号的弹丸位置仍变化；世界 yaw 固定，相机跟随车体居中，面板约 61 FPS |
| 资源分发 | config/browser-assets.lock.json 固定 Pyodide 0.29.5 和 14 个资源 SHA-256；下载和 bundle 不进入 Git；prepare 支持离线重建 |
| 构建矩阵 | .github/workflows/checks.yml 配置 Linux/Windows/macOS 原生/WASM Rust 检查；本轮没有远程 Runner 执行结果 |

协议语义检查不是完整协商服务/任意订阅实现。MessagePort 夹具使用显式 QA 回送路径，真实 Python 批次的请求/响应另由 600 tick 闭环覆盖；负夹具不作为运行时传感器输入。配置为全向时，“差速不能横移”领域夹具仍使用它明确声明的差速上下文。

## 性能与包体

报告 JSON 保留版本、配置/Cargo.lock/构建产物/bundle 摘要以及逐项判定。Firefox 启用时间精度限制，小于 1 ms 的 Core 调用可能显示为 0，不能理解为零计算成本。

- Release Core WASM 约 **2.1 MiB**；固定 Pyodide 资源总计 **12,708,949 bytes**。这是唯一文件大小总和；两个解释器分别加载，不等于页面总下载或完整安装体积。
- 新 Worker 启动约 **2.4 s**，字段为 worker_startup_ms；复用已经启动的浏览器和 OS 文件缓存，未测机器冷启动。原生当前配置启动/时间分布另见 M1 current-profile。
- Core WASM 内存分配约 **1.25 MiB**、可信 Pyodide **24 MiB**、玩家 Pyodide **20 MiB**；这是已分配的线性内存，不是 RSS，也不是硬额度或峰值内存保证。
- Python 批次往返 p50 约 **1 ms**、p95/最大约 **2 ms**。普通闭环 Authority tick p50 约 **5–6 ms**、p95 约 **16 ms**；武器练习视图 p95 **22 ms**、最大 **26 ms**。Core JSON 调用 p95 约 **1 ms**。Authority 包含 Schema/视图/序列化，后续增加机器人前必须评估长尾和预算。
- 从加载阶段开始采样约 740 个 rAF 帧，正常/故障/武器场景最大间隔约 **17–18 ms**。本机主线程没有运行物理或 Python，也没有采样到 >50 ms 的停顿。Firefox 此处没有独立 Long Tasks API 报告；帧采样不能证明所有机器和浏览器都无长任务。

物理仍为固定 60 Hz / 4 子步，观测 30 Hz、算法 10 Hz；rAF 独立运行。超载/后台降频会影响墙钟进度，不能外推为硬实时保证。

## 安全检查与未提供的保证

实际 Python JS 桥探针通过 8 项：无 core_call 宿主句柄、无 Authority 源码、无私有配置、无宿主 /etc/passwd、UI origin 连接被 CSP 阻止、外网连接被 CSP 阻止、嵌套 Worker 被阻止、fork 不可用。嵌套 Worker 通过实际执行/错误事件判断，不能把构造器返回对象当作成功启动。HTTP 测试另确认 Runtime origin 无 Core/配置/部署/API 路由，玩家 bundle 不含 Host、Schema 或配置。

Runtime 仍可读取自己 origin 的固定资源并写自己的 MEMFS；没有浏览器硬内存/磁盘/CPU 配额，没有做破坏性 OOM 压力测试，也不保证抵御所有 JS 消息洪泛/DoS。普通 CPython 子进程的文件/网络没有 OS 沙箱。本地公开场景启动资源可被设备所有者检查；远程隐藏世界与公平比赛必须由服务器 Authority 和强化沙箱保护。

## 可重复命令

```bash
python3 tools/build.py --offline
python3 tools/build.py --offline --wasm
python3 tools/build.py --offline --wasm --release
python3 tools/prepare_browser.py --offline
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs
node tests/test_wasm.mjs
python3 docs/tools/check_design.py
```

本轮 Python **53** 项、Rust **10** 项、渲染 JS **9** 项及 WASM 集成对比通过。首次准备 Pyodide 需去掉 --offline；项目只有依赖锁，没有提交下载资源。

真实浏览器测试先启动 `python3 tools/tankbot.py browser --chassis omnidirectional --browser-qa` 与启用 Marionette 的 Firefox，再执行 `python3 tools/browser_m2.py`。差速修改服务参数并指定工具输出路径；故障服务增加 `--fault infinite_loop`，工具增加 `--expect-fault`；武器服务增加 `--robot-demo --view weapons-practice`，工具增加 `--expect-weapons`。逐次关闭旧服务/会话，不能并发驱动同一浏览器。

## 平台与 ADR 复审

| 平台/能力 | 本轮状态 |
| --- | --- |
| Linux 原生 CPython + Rust | 实测；可信个人代码；无 OS 沙箱 |
| Linux Firefox WASM + Pyodide | 实测；单机器人、双 Worker/CSP；资源限制如上 |
| Node WASM | 实测构建/完整快照对比；不替代浏览器安全证据 |
| Windows/macOS 原生/WASM | CI 配置完成，尚无执行结果；不声明支持 |
| Chromium/WebKit、移动端 | 未执行；不声明支持 |
| 远程多人/Arena/第三方服务器执行 | 未实现；OS 隔离准入仍必需 |

ADR-0002 接受已验证范围的 Rust/Rapier；ADR-0020 接受共享 Authority 与局部浏览器部署。ADR-0003 因编辑器/Phaser 尚未验证保持 Proposed；ADR-0013 因完整安全矩阵、OS 隔离与配额未通过保持 Proposed。

M2 的其他平台执行项仍开放。可并行推进 M3a：非覆盖多文件 Workspace、不可变部署快照与失败保留旧部署；此次未开始 M3。
