# 12 设计验证、研究依据与开放问题

## 目的、范围与证据层次

当前实现为应用配置2.1、十二关、原生/浏览器Runtime、同步模块图、多文件编辑部署、C2滤波回放试点和项目维护；Navigation含轮控、里程计、GPS/EKF、航点、连续路径和已知地图规划。运行profile已拆分声明准入/墙钟，默认仍experimental。当前事实与提交状态见 [本轮核对](reports/DOCUMENTATION_STATE_SYNC_20261110.md)，接口由领域规范负责，验收由各历史报告记录，未来能力由开放项追踪。

本轮开始HEAD为7c065ab、工作区干净；Runtime profile等不是本轮新增代码。历史M0–M3研究/计数保留在文末明确标注的小节，不以当时范围否定后续实现，也不将历史通过计数称作本轮检查。完整平台隔离ADR-0013仍为Proposed，CI配置不是平台通过证据。

## 需求与接口追踪

| 需求领域 | 权威规范 / ADR | 当前检查与后续验收方向 |
| --- | --- | --- |
| 产品愿景、模式、持续学习 | 01、09、36；0001/0049 | 十二关双主线、主线内代码复用；未来课程另行确认 |
| 逻辑/进程/部署、Rust/C++ | 02；0001/0002 | 无头/原生/WASM 探针与平台矩阵 |
| Web 表现/编辑器 | 02、06、17；0021 | 只读 DTO、多文件/Vim/焦点测试 |
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
- sample tick、delivery tick、activation tick 和 output commit tick 分开；M1 确认 60 Hz 物理/4 子步、30 Hz 轮组/IMU、10 Hz 算法；M4 另经用户确认实现 10 Hz Radar，保持原固定提交语义。
- 连续速度使用 `/robot/cmd_vel` / `twist@1`，保留 vx/vy/wz 对应的 linear.x/y、angular.z；payload 无执行起止时间。Host 决定内部提交时刻，Core 内底盘控制器按生成时间与 cmd_vel_timeout 检查新鲜度。差速模型不能横移，M1 已实现四轮径向全向轮的聚合刚体模型与 JointState 观测。
- Workspace revision 可编辑，DeploymentArtifact 不可变；测试报告绑定摘要；重启/部署不隐含重置 World，reset/seek 才新建 run。
- JSON Schema 只处理结构；PSD、帧关系、跨字段时间与权限有独立验证责任。文档检查不声称实现这些领域验证器。

## 统一检查入口与文档专项

```bash
python3 tools/check.py --offline
# 纯文档同步可只运行以下专项，不声称已执行全部回归：
python3 docs/tools/check_design.py
python3 tools/export_profile.py --check --offline
git diff --check
```

标准入口依次运行自动发现的普通Node测试、Python、Rust、文档与生成配置一致性，失败返回非零。`npm test`仅为普通前端；构建后WASM另跑 `npm run test:wasm`，真实UI另用 `npm run test:browser -- --help` 选择流程。文档专项需要requirements.txt中的jsonschema/referencing/PyYAML等依赖，离线注册本地Schema，不访问$id域名。具体入口和范围见 [38](38_ENGINEERING_AND_ALGORITHM_LAB.md)。

检查范围：Markdown 本地链接与代码块、ADR 状态和索引、严格 JSON、Draft 2020-12 Schema、自包含正例、结构负例与领域案例分层、Python 示例语法、行尾空白。Python 示例仅 AST 解析，此工具不导入 SDK；另由 M1 测试执行 SDK 片段。早期检查仅针对初始化后的文档；当前`git diff --check` 检查已跟踪改动；新增文件仍需检查。工具对所有 Markdown 检查空白，JSON 做完整格式检查；也可逐文件运行 `git diff --no-index --check /dev/null <path>`，退出码 1 仅表示文件差异，实际空白告警不能忽略。

当前检查计数由工具输出，避免手工统计与文档变更漂移。M1 初版历史验证包括：22 项单元/集成测试（其中一项接入 10 个文档协议领域案例）、两底盘各 600 tick 测量、同构建执行器重放、原生/WASM 构建与执行、Firefox 页面和按键验证。基准 JSON 记录实际配置和构建摘要，见报告。

`test_protocol_fixtures.py`直接接入10个协议领域负例；另外的Manifest/event/连线/策略案例并未因此全部绑定到该夹具循环。当前模块图和权限已另有 `test_robot_graph.py`、`test_level_plugins.py` 等行为回归，不能继续将功能本身统称未实现，也不能声称所有文档案例均已逐项映射。OS沙箱、其他平台和Arena仍需独立证据。

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
| 强隐藏与操作反馈 | 局部观测/估计、逐关授权实时标量及终局评估分开 | 反馈有推断性，教学效果与信息oracle仍需评估 |
| 自动模板与代码所有权 | exclusive-create、预览、三方合并、revision CAS | 用户需理解少量迁移冲突 |
| 前期公开地图后期未知地图 | 使用新场景与 seed，不声称能撤回已知信息 | 玩家可能记忆通用地图规律 |
| 跨平台与强服务端沙箱 | 共享语义，按平台采用不同 Adapter/安全承诺 | 桌面任意第三方代码能力可能后置 |
| 一个 worker 与每模块预算 | 模块预算用于准入/诊断，硬限制在可信 Supervisor 的机器人批次 | 无法把共享解释器内模块彼此安全隔离 |

## 当前完成子项与剩余验证任务

| ID | 已实现/已接受的子项 | 仍待决定或验证的部分 | 权威入口 |
| --- | --- | --- | --- |
| O01 | Rust/Rapier已在Linux原生/Firefox WASM范围接受 | 其他OS/浏览器完整流程、规模与维护成本 | 02、ADR-0002、16 |
| O02 | Canvas/CodeMirror/Vim、类型帮助与多文件编辑部署 | 其他平台键位/编辑体验、独立静态Web存储 | 17、19、ADR-0021 |
| O03 | 双origin/Pyodide Worker与可信共享Authority已实现 | 浏览器硬资源隔离、后台/休眠与其他浏览器 | 16；ADR-0013完整安全组合仍Proposed |
| O04 | 本机可信本人代码与受限浏览器Worker | 服务端OS沙箱、第三方上传、CPU/内存/网络攻击测试 | 08、M8上线门 |
| O05 | 固定60Hz/4子步、按实例采样、10Hz算法、6tick门；独立后端profile及流式基准 | 更多完整UI尝试、设备/平台与整局截止可靠性；未证明<1% | 07、41、11月7日Runtime报告 |
| O06 | 严格JSON、现用消息/地图/路径与原生-WASM夹具 | 大规模scan/地图瓦片、多机器人与必要时的编码优化；公共Envelope与私有帧配额分开 | 03、27、40 |
| O07 | revision/ledger、预览迁移、旧源码和完整工程恢复 | 已发布SDK兼容窗口、云同步、会话artifact GC | 06、17、38 |
| O08 | 固定尝试profile、权限和可重复本机基准 | 远程权威、赛制硬件/资源类别与Arena公平性 | 08、41、M8 |
| O09 | 逐关实时RMSE、C2授权回放和失败复现 | 完整Lab、多模块/控制器成对闭环与信息oracle评估 | 04、38 |
| O10 | 固定公开帧、Navigation编码器/GPS特定时间对齐 | 通用动态TF、任意异步融合与非零安装 | 32、35 |
| O11 | Weapons弹丸显示、Radar与匿名装甲已实现 | scan、听觉模型和通用接触方向观测 | 04、30、39 |
| O12 | 已注册消息、跨Adapter/Schema/SDK夹具及当前兼容规则 | Protocol 1.0首次发布冻结、正式网络会话/服务集 | 03、schemas索引 |
| O13 | Twist/JointState等采用ROS习惯，PolarTargetEstimate元组统一 | 首次SDK发布审查命名/单位差异；不声称完整ROS消息兼容 | 03、05、ADR-0014 |
| O14 | 两种底盘、完整模型、理想轮观测；差速轮电压电机已实现 | 全向轮电机、空转/轮滑、更多地面模型与热替换 | 29、32、33 |

当前课程阈值与模型已经确认，不列为待选默认，也不在文档同步中调整。玩家全局规划已按用户确认实现为 [42](42_NAVIGATION_GLOBAL_PLANNING.md)，其验收单列；局部避障、IMU融合、建图/SLAM课程仍为Planned，见 [39](39_NAVIGATION_COURSE_PROPOSALS.md)。C4裁判生成路径与C5玩家规划是不同合同。发布许可/资产政策、账号与服务方案仍需维护者决策。

## 历史研究来源与适用限度（M0/M1）

下表保留2026-10-20/21研究时的访问和选型记录；其中“本轮”“当前”等指当时资料，不是2026-11-10重新访问结果。当前依赖以仓库锁文件和Accepted ADR为准。滚动stable不是依赖锁，后续升级需另行核实；本次没有重新抓取外部来源。

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

所有需求领域有负责人模块、数据流、接口、替代与验收；JSON/Python 例子和术语一致；Accepted/Proposed 不混写；不把设计样例当实现；没有未授权真值路径；现有玩家代码迁移不覆盖。M0 以此结束；后续 M1/M1b 已按授权完成本机实现与验收，见 [M1b 报告](reports/M1B_VALIDATION.md)；后续已授权阶段的当前状态以路线图及上述最新验收为准。

## 历史：M1更新

M1当时使用 `python3 -m unittest discover -s tests -v` 和 `python3 tools/measure_m1.py` 验证物理、worker及双底盘探针；现行统一入口已改为上节tools/check.py。文档工具不替代权限/运行测试。M1增加joint_state@1和SimulationProfile，旧encoder@1语义保留。

O01 已得到 Linux/Node WASM 的部分证据，完整浏览器 Worker 和其他 OS 保持开放；O05 的 60/30/10 Hz 和 20 ms 批次在本机验证，Arena/慢设备需另测；O14 的 M1 聚合全向模型已完成，详细轮电机/轮滑仍需新模型确认。以上为 M1 阶段历史结论；当前 ADR 状态以索引和以下 M2 证据为准，不以历史计数推断实现。

## 历史：M2更新与当时门槛

M1/M1b [收尾](reports/M1_CLOSEOUT.md) 后，M2 已完成共享 Authority / ModuleRunner 的浏览器双 Worker、49 个 Envelope 正反夹具在真实 MessagePort/IPC/WebSocket/In-Process/Replay 的一致性、实际文件/网络/宿主句柄负例、死循环终止与新 run 恢复、程序炮台/开火、资源与 UI 帧间隔测量。配置内部升级 1.4，没有改变已确认物理和公共协议。

O01 已在 Linux 原生与 Firefox WASM 范围接受，ADR-0002 改 Accepted；O03 的本地原型路径由 ADR-0020 接受，但 ADR-0013 的完整安全组合仍 Proposed。O02 的本机组合已由 M3 实验接受（ADR-0021），其他平台仍待验收。O05 单机器人 20 ms 批次已测，Authority 视图校验的时间长尾仍需性能预算；O06 的夹具相等不代表大规模 scan/地图已测。

本轮 Python 53 项、Rust 10 项、渲染 JS 9 项及两底盘各 600 tick WASM/原生全快照比较通过。具体命令、摘要、平台矩阵与测量限制见 M2 报告。Windows/macOS 和 Chromium/WebKit 未实际执行；CI 矩阵是待运行的自动化入口。浏览器无硬内存/磁盘配额，未做破坏性 OOM 压力测试；服务端 gVisor/microVM、安全依赖准入、公平配额仍是 M8 上线门。

## 历史：M3/M4初次验收

M3 多文件编辑、非覆盖模板、CAS/文件锁、快照报告、独立 Test Runtime、tick 边界部署与显式回滚已验证。历史测试与原生/Firefox UI 记录见 [M3 报告](reports/M3_VALIDATION.md)。单模块 profile、观察式仿真测试、会话内 Ready 和启动器存储限制见 [17](17_EDITOR_AND_DEPLOYMENT.md)。M4 新增模型已逐项确认，C0–C2、两种跟踪法、结束后评分及原生/Firefox 通关记录见 [M4 报告](reports/M4_VALIDATION.md)。
