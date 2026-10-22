# 12 设计验证、研究依据与开放问题

## 目的、范围与完成定义

汇总需求覆盖、检查证据、假设与下一步准入条件，防止“设计接受”被误读成“技术验证完成”。M0 原范围为离线文档；用户后续授权 M1，当前已有原生 Core、Host、SDK 子集和 Web 原型，实际证据见 [M1 报告](reports/M1_VALIDATION.md)。完整沙箱仍未实现；本轮 M1 收尾与 M2 本机浏览器范围见 [报告](reports/M2_VALIDATION.md)。初版资料核实日期为 2026-10-20；当前基线 `m1-0.1`，2026-10-21 按 ROS 习惯修订速度接口。新增 ROS 参考链接因网络不可达尚未在线复核，不能当作已验证的滚动版本默认行为。

## 需求与接口追踪

| 需求领域 | 权威规范 / ADR | 后续实现验收 |
| --- | --- | --- |
| 产品愿景、模式、持续学习 | 01、09；0001 | C0–C7 可复用项目，问题驱动评价 |
| 逻辑/进程/部署、Rust/C++ | 02；0001/0002 | 无头/原生/WASM 探针与平台矩阵 |
| Web 表现/编辑器 | 02、06；0003 | 只读 DTO、多文件/Vim/焦点测试 |
| JSON、权限、版本和 Transport | 03；0004/0005/0014 | 结构、时序、授权、ROS 风格速度流、Adapter 等价夹具 |
| 三层状态、选源、初值/帧/显示 | 04；0006/0007 | 错估计、无估计、多源、漂移与泄漏回归 |
| SDK、Contract、渐进 API | 05；0008 | 函数/类等价、缺输入、依赖/事件/重置测试 |
| Workspace、模板/Manifest/迁移 | 06；0009 | 文件不覆盖、CAS、回滚、跨平台路径测试 |
| Edit/Test/Deploy | 06；0012 | 摘要绑定、staging 失败保旧、原子切换 |
| 物理/传感器/时钟/确定性/Replay | 07；0010/0011/0014 | 固定 tick、乱序/截止、底盘 watchdog、同构建录制重放 |
| 不可信 Python、安全与公平 | 08；0001/0006/0013 | OS 级资源/网络/文件测试与服务器上线门 |
| 关卡教学、Lab、Arena | 09、10 | 可玩性、输入回放/闭环区分、权威评分 |
| Q1–Q15 | 11 | 对应领域测试，不留只有问题的条目 |
| 后续 Agent 规则 | 根 AGENTS.md | 新任务阅读、ADR/接口/测试同步 |

## 跨文档一致性基线

- 全部 Envelope 使用 `protocol_version`、`message_type`、`channel`、`sequence_number`、`simulation_tick`、`simulation_time_ns`、`run_id`、`publisher_id`、`request_id`、`frame_id`、`schema`、`payload`；不存在另一套 kind/data 别名。
- 玩家位姿只写候选；Selector 独占 `/robot/localization/pose`。`/system/pose` 不是公开 Topic，系统源许可不会因候选超时自动恢复。
- `world` 是私有物理系，`map` 与 `odom` 是公开声明系；显示插值不反馈物理。权威状态不进入 UI/SDK 的通用序列化接口。
- sample tick、delivery tick、activation tick 和 output commit tick 分开；M1 确认 60 Hz 物理/4 子步、30 Hz 轮组/IMU、10 Hz 算法；5 Hz Radar 仍未实现。
- 连续速度使用 `/robot/cmd_vel` / `twist@1`，保留 vx/vy/wz 对应的 linear.x/y、angular.z；payload 无执行起止时间。Host 决定内部提交时刻，Core 内底盘控制器按生成时间与 cmd_vel_timeout 检查新鲜度。差速模型不能横移，M1 已实现四轮径向全向轮的聚合刚体模型与 JointState 观测。
- Workspace revision 可编辑，DeploymentArtifact 不可变；测试报告绑定摘要；重启/部署不隐含重置 World，reset/seek 才新建 run。
- JSON Schema 只处理结构；PSD、帧关系、跨字段时间与权限有独立验证责任。文档检查不声称实现这些领域验证器。

## 本轮离线检查与可重复命令

```bash
python3 docs/tools/check_design.py
git status --short
git diff --check
```

检查工具需要现有 Python 环境具备 `jsonschema` 与 `referencing`；M0 检查使用已有环境；M1 requirements.txt 明确记录 Python 验证依赖。工具离线注册本地 Schema，不访问 `$id` 示例域名。

检查范围：Markdown 本地链接与代码块、ADR 状态和索引、严格 JSON、Draft 2020-12 Schema、自包含正例、结构负例与领域案例分层、Python 示例语法、行尾空白。Python 示例仅 AST 解析，此工具不导入 SDK；另由 M1 测试执行 SDK 片段。早期检查仅针对初始化后的文档；当前`git diff --check` 检查已跟踪改动；新增文件仍需检查。工具对所有 Markdown 检查空白，JSON 做完整格式检查；也可逐文件运行 `git diff --no-index --check /dev/null <path>`，退出码 1 仅表示文件差异，实际空白告警不能忽略。

当前检查计数由工具输出，避免手工统计与文档变更漂移。M1 初版历史验证包括：22 项单元/集成测试（其中一项接入 10 个文档协议领域案例）、两底盘各 600 tick 测量、同构建执行器重放、原生/WASM 构建与执行、Firefox 页面和按键验证。基准 JSON 记录实际配置和构建摘要，见报告。

剩余 4 个文档领域案例涉及通用 Manifest/event/连线及独立策略配置接口，不混算为 M1 已完成能力。OS 沙箱、Windows/macOS 与 Arena 仍未验证；浏览器双 Worker 与多 Adapter 等价已在下方 M2 更新给出证据。

## 实现阶段如何保持文档与 API 一致

1. 以 Schema 注册表生成或核查 TS/Python 序列化类型；不要让三套手写字段无对照演化。模块 Contract 的入口/签名在沙箱内做 import 与类型检查。
2. 把本轮正例和结构负例接入真实 Router；把领域负例接入独立数值/时序/Frame Registry/权限验证器。错误码和拒绝位置须一致。
3. 从 Markdown 提取可执行示例到文档 CI；SDK 完成后进行 import、Contract 与行为测试，不能只看片段语法。
4. 同套夹具经过 In-Process、Worker、IPC、WebSocket、Replay/Test，比较接受/拒绝和逻辑 tick，避免 Adapter 旁路。
5. 做最小端到端泄漏测试：两世界仅隐藏状态不同而授权观测相同，比较下发 DTO/效果/音频/相机。另测试输入本身可以合法区分世界的情况，避免把正常感知误判为泄漏。
6. 对协议发布 profile 留兼容夹具；公共字段、单位或频道变化同步更新 ADR、Schema、SDK、正文、样例和测试。PR 报告实际执行命令与限制。

## 已识别的需求张力与处理

| 张力 | 当前处理 | 剩余风险 |
| --- | --- | --- |
| 离线运行且隐藏全部真值 | 本地实施教学边界；对抗防作弊依赖远程 Authority | 本机逆向、调试器读取内存 |
| 实时执行且算法完全确定 | 固定逻辑提交，记录实际超时；受控测试另设执行 profile | 硬件/OS 抖动影响预算结果 |
| 强隐藏与操作反馈 | 只显示局部观测/估计，停止后提供授权评估 | 可玩性与信息难度待用户测试 |
| 自动模板与代码所有权 | exclusive-create、预览、三方合并、revision CAS | 用户需理解少量迁移冲突 |
| 前期公开地图后期未知地图 | 使用新场景与 seed，不声称能撤回已知信息 | 玩家可能记忆通用地图规律 |
| 跨平台与强服务端沙箱 | 共享语义，按平台采用不同 Adapter/安全承诺 | 桌面任意第三方代码能力可能后置 |
| 一个 worker 与每模块预算 | 模块预算用于准入/诊断，硬限制在可信 Supervisor 的机器人批次 | 无法把共享解释器内模块彼此安全隔离 |

## 开放问题与验证任务

| ID | 推荐假设或暂定方案 | 证据/决定门 | 影响 |
| --- | --- | --- | --- |
| O01 | Rust/Rapier2D 优先，C++/Box2D 备选 | M1 构建、CCD、600 tick 和维护成本报告；ADR-0002 | 核心工具链与物理 |
| O02 | TS/Phaser/CodeMirror 6 + 可选 Vim | M2/M3 包体、渲染/编辑、迁移仓库来源与许可证；ADR-0003 | 前端依赖与浏览器矩阵 |
| O03 | Pyodide 独立 origin/Worker | M2 CSP/网络/JS 桥/终止/启动探针；ADR-0013 | 浏览器安全与性能 |
| O04 | gVisor 或 microVM，桌面按 OS 验证 | M8 前文件/网络/CPU/内存攻击与成本报告；ADR-0013 | 第三方代码上线硬门 |
| O05 | 60/30/10/5 Hz，单机器人批次 20 ms 起测 | M1/M2/M6 延迟、控制效果、资源准入报告 | 预算和教学参数 |
| O06 | 严格 JSON + 64 KiB Envelope | M2 实际扫描/地图负载；必要时分瓦片，之后才评估二进制 | 消息吞吐与回放大小 |
| O07 | 首期保留上一已发布 SDK minor 的兼容窗口 | 首次 SDK 发布前评估维护成本/安全更新 | 玩家项目寿命 |
| O08 | 固定 profile/硬件类别、多 seed/换出生位 | M8 公平性与超时分布基准 | Arena 评分可信度 |
| O09 | 停止后真值评估、活跃时聚合反馈 | M4/M7 教学/信息 oracle 测试 | 学习反馈与保密 |
| O10 | 首期只处理公开固定帧与玩家 map/odom | M5 决定是否需要通用动态变换 Topic | 多模块坐标复杂度 |
| O11 | 局部 scan、弹丸/音频效果后补独立 Schema | M4/M5 观测可玩性和泄漏测试 | 关卡与表现权限 |
| O12 | v1 草案冻结前补齐首发频道/服务 | M2/M3 协商、选源、模块诊断的注册与兼容测试 | 公共 API 发布 |
| O13 | 其他机器人消息逐项参考 ROS 命名/类型/时间习惯 | SDK 发布前审查现有 Pose2D/IMU 等差异，不冒充完整 ROS 消息 | 学习迁移与接口一致性 |
| O14 | 全向底盘共用 Twist，新增按轮名状态的传感器 | M1 两底盘模型、joint_state Schema/SDK 和 600 tick 测试已交付；轮电机/空转仍不在模型内 | 全向轮扩展可行性 |

这些项目都有推荐方向，但没有被文档工作“解决为事实”。参考设备、性能门槛、项目许可证/资产政策、账号/存储服务方案仍需产品与维护者决策；后两项不阻塞 M1。

## 研究来源与适用限度

只使用第一方资料支撑技术事实；比较结论是针对 TankBot 的架构判断，不是测量结论。滚动 stable 文档不是依赖锁，实际采用时重新核对并固定版本。

| 来源 | 本轮用于判断什么 / 不证明什么 |
| --- | --- |
| [Rust WASM target](https://doc.rust-lang.org/stable/rustc/platform-support/wasm32-unknown-unknown.html) | 最小目标的 OS API 限制；不证明所有 crate 可编译 |
| [Rust Ownership](https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html) | 所有权与安全内存模型；FFI/unsafe 仍需审核 |
| [Emscripten JS interop](https://emscripten.org/docs/porting/connecting_cpp_and_javascript/) | C/C++ 与 JS/WASM 接口可选路径；非 TankBot 构建结果 |
| [Rapier](https://www.rapier.rs/docs/)、[确定性条件](https://rapier.rs/docs/user_guides/templates/determinism) | 候选库能力与条件；不同版本 feature 需核对，不转写成全应用保证 |
| [Box2D FAQ](https://box2d.org/documentation/md_faq.html)、[Simulation](https://box2d.org/documentation/md_simulation.html) | 当前 C API、确定性和回滚限制；不假设任何快照都能复现 |
| [Pyodide Worker](https://pyodide.org/en/stable/usage/webworker.html)、[Interrupt](https://pyodide.org/en/stable/usage/keyboard-interrupts.html) | UI/计算隔离与中断条件；不是服务端沙箱 |
| [MDN Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Using_web_workers) | Worker 环境及可用 API；不能假设没有网络 |
| [Phaser Game](https://docs.phaser.io/phaser/concepts/game) | 表现循环候选；不让其成为物理权威 |
| [CodeMirror 官方迁移公告](https://github.com/codemirror/dev)、[当前仓库链接](https://code.haverbeke.berlin/codemirror/dev) | GitHub 镜像声明迁移；新站与官网本轮抓取 403，完整 API/包版本待验证，不能推断项目停止维护 |
| [CM6 Vim 扩展](https://github.com/replit/codemirror-vim) | 独立扩展候选；需版本/维护和键位验证 |
| [Tauri Security](https://v2.tauri.app/security/) | 桌面桥接安全需显式授权；桌面壳不是 Python 沙箱 |
| [Tokio Tutorial](https://tokio.rs/tokio/tutorial) | Rust Host 的网络运行时可选项；不放入纯 Core |
| [gVisor Security](https://gvisor.dev/docs/architecture_guide/security/) | 强化隔离仍依赖宿主配额/网络控制，侧信道未消除 |
| [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) | 结构 dialect 和本地引用组织；语义与权限需另外实现 |
| [Twist](https://docs.ros.org/en/rolling/p/geometry_msgs/msg/Twist.html)、[官方源码](https://github.com/ros2/common_interfaces/blob/rolling/geometry_msgs/msg/Twist.msg) | 新接口参考 linear/angular Vector3 形状；2026-10-21 浏览工具连接失败且直连超时，待在线复核 |
| [diff_drive_controller](https://control.ros.org/rolling/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html)、[mecanum_drive_controller](https://control.ros.org/rolling/doc/ros2_controllers/mecanum_drive_controller/doc/userdoc.html) | 底盘适配与控制器超时的参考入口；本轮网络不可达，不据此宣称某版本默认值、支持轴或拒绝行为；TankBot 具体语义见 ADR-0014 |

## 最终审查准则

所有需求领域有负责人模块、数据流、接口、替代与验收；JSON/Python 例子和术语一致；Accepted/Proposed 不混写；不把设计样例当实现；没有未授权真值路径；现有玩家代码迁移不覆盖。M0 以此结束；后续 M1/M1b 已按授权完成本机实现与验收，见 [M1b 报告](reports/M1B_VALIDATION.md)；下一阶段按 M2a 范围开展。

## M1 更新

新验收入口为 `python3 -m unittest discover -s tests -v`（真实物理/worker/HTTP/SDK），`python3 tools/measure_m1.py`（双底盘 600 tick、同构建重放和原生/WASM 构建探针）。文档工具仍只检查结构/链接，不替代权限或运行测试。M1 的范围与源码路径见报告；Schema 已新增独立 joint_state@1 和 SimulationProfile，旧 encoder@1 含义未改。

O01 已得到 Linux/Node WASM 的部分证据，完整浏览器 Worker 和其他 OS 保持开放；O05 的 60/30/10 Hz 和 20 ms 批次在本机验证，Arena/慢设备需另测；O14 的 M1 聚合全向模型已完成，详细轮电机/轮滑仍需新模型确认。以上为 M1 阶段历史结论；当前 ADR 状态以索引和以下 M2 证据为准，不以历史计数推断实现。

## M2 更新与剩余门槛

M1/M1b [收尾](reports/M1_CLOSEOUT.md) 后，M2 已完成共享 Authority / ModuleRunner 的浏览器双 Worker、49 个 Envelope 正反夹具在真实 MessagePort/IPC/WebSocket/In-Process/Replay 的一致性、实际文件/网络/宿主句柄负例、死循环终止与新 run 恢复、程序炮台/开火、资源与 UI 帧间隔测量。配置内部升级 1.4，没有改变已确认物理和公共协议。

O01 已在 Linux 原生与 Firefox WASM 范围接受，ADR-0002 改 Accepted；O03 的本地原型路径由 ADR-0020 接受，但 ADR-0013 的完整安全组合仍 Proposed。O02 在 M3 编辑器验证前保持 Proposed。O05 单机器人 20 ms 批次已测，Authority 视图校验的时间长尾仍需性能预算；O06 的夹具相等不代表大规模 scan/地图已测。

本轮 Python 53 项、Rust 10 项、渲染 JS 9 项及两底盘各 600 tick WASM/原生全快照比较通过。具体命令、摘要、平台矩阵与测量限制见 M2 报告。Windows/macOS 和 Chromium/WebKit 未实际执行；CI 矩阵是待运行的自动化入口。浏览器无硬内存/磁盘配额，未做破坏性 OOM 压力测试；服务端 gVisor/microVM、安全依赖准入、公平配额仍是 M8 上线门。
