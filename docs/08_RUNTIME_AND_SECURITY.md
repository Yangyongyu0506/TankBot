# 08 Python Runtime、安全边界与 Arena

## 目的、范围与威胁模型

玩家源码、import、依赖、测试、checkpoint 和所有 Runtime 输出均不可信。对手可能死循环、耗尽资源、伪造消息、读取文件/网络、利用原生扩展或跨玩家通信。需要保护 Host、其他玩家、秘密地图/状态、比赛公平性和存储。ADR-0001/0006 接受安全边界；ADR-0013 的具体平台方案为 Proposed。

可信基包括 Core Host、Supervisor、Router/权限检查、View Gateway、评分器、部署打包器和已审核的沙箱配置。UI 和客户端自报成绩均不可信。Python SDK 的校验只改善错误提示，安全必须在 SDK 之外重做。强制隔离原则来自 Accepted ADR-0001/0006；具体平台技术保持 Proposed ADR-0013，不能据此推迟安全边界。

## 平台方案与保证边界

| 环境 | 建议实现 | 有效边界 | 必须承认的限制 |
| --- | --- | --- | --- |
| 浏览器单人 | Core WASM Worker + 独立 Pyodide Worker | 消息传递、不共享 World、可终止 worker | Worker 不是服务器沙箱；本机用户能读客户端内存 |
| 本地桌面 | 独立 CPython worker；提供受限模式 | 故障隔离、明确输入与运行目录 | 普通子进程没有足够文件/网络隔离；OS 差异待验证 |
| 服务器/Arena | Linux 上每机器人独立强化沙箱 | 无 Host FS/网络、系统资源配额、可信桥接 | gVisor/microVM 等需基准与攻击测试后选型 |

本地第一版若只具进程隔离，必须在产品中清楚标注“仅运行本人可信代码”，不得接收任意下载脚本或把该模式叫安全沙箱。远程第三方代码在服务器隔离验收前禁用，不能用“内部测试”绕过边界。Windows/macOS 在服务器级本地隔离未验证前，可采用浏览器运行或远程 Runtime。

## 浏览器设计

Pyodide Worker 避免同步 Python 阻塞主 UI；它与 Core Worker 不同，只有专用 MessagePort，任何 port 消息仍按 Protocol 校验。不得给 Python 传 Core 对象、共享内存、账号令牌或桌面原生桥。

Pyodide 可访问 JS 桥，删除 `import js`、过滤 builtins 或 AST 扫描均不是可靠隔离。建议把执行环境置于无账号、无 Cookie、无私有接口的独立 origin，通过受控 iframe/端口与主应用通信；CSP 限制加载与连接，运行 origin 仅提供固定只读 Runtime 资源。浏览器具网络 API，因此“Worker 内无网络”不能凭约定成立；真正的网络策略、资源预加载及 iframe/CSP 组合须专项验证。

不要把主应用用户 Workspace 全部挂进共享 JS/文件系统，只装入选定部署快照。跨 origin 与 `SharedArrayBuffer` 的 COOP/COEP 要求需测试，不让其成为 MVP 必需条件。优先无共享内存的 MessagePort；合作式 interrupt 可改善体验，但玩家能捕获异常，最终兜底是 Supervisor 调用 `terminate()` 并创建新 worker。

资料依据：[Pyodide Worker](https://pyodide.org/en/stable/usage/webworker.html) 描述计算与 UI 分线程；[interrupt 文档](https://pyodide.org/en/stable/usage/keyboard-interrupts.html) 说明共享中断缓冲条件。它们不提供服务端文件/网络沙箱保证。

## 服务器隔离设计

建议评估 gVisor 或 microVM，普通容器作为构建/管理层而不是完整的安全结论。沙箱配置至少包含：

- 非特权 UID/GID、独立 namespace、删除 capabilities、禁止 ptrace/Host PID/设备与特权 syscall；只读系统镜像和部署文件。
- 独立临时可写目录和有限 checkpoint 区；不挂 Host 家目录、Git 凭据、Docker socket、秘密评分器或其他用户数据。
- 外部网络默认拒绝，禁止 DNS、loopback 到 Host 服务、云 metadata 和跨 worker 通信。与 Supervisor 的 IPC 只通过预先建立的受控通道。
- cgroups/等价资源控制：CPU、内存、pids；另限文件数、文件大小、日志、消息、磁盘与运行墙钟。限制在 Host 强制执行。
- 依赖镜像固定摘要、无运行时包安装、无任意 native wheel。Python 标准库在沙箱里也不因此可信。

每机器人独立沙箱是首期选择；同机器人内模块共享故障域，与 05 一致。Host 解析来自沙箱的数据时限制长度、递归深度和分配，不能信任 `publisher_id`、预算统计或“验证已通过”标记。沙箱技术不代替协议与 View Policy。[gVisor 安全模型](https://gvisor.dev/docs/architecture_guide/security/) 同样要求宿主资源配额与网络策略，且不承诺消除硬件侧信道。

## 初始预算与故障策略

候选 profile：每机器人 1 个 worker、内存 256 MiB、进程/线程上限 16、可写数据 16 MiB、每墙钟秒日志 32 KiB、整机器人单次激活批次墙钟上限 20 ms。模块请求预算之和须经过 Host 准入并低于该硬限额；不能把共享 worker 的内部模块当成独立安全主体。Runtime 初始化可有独立 5 s 上限；Pyodide 引擎自身内存占用需单独测量，浏览器无法可靠实现与 cgroups 等价的硬内存限额，所以不能机械照搬 256 MiB 声明。

| 故障 | Supervisor 动作 | 游戏后果 |
| --- | --- | --- |
| 语法/import/setup 异常 | 拒绝 staging，记录用户可读定位 | 旧部署继续运行 |
| 回调异常 | 拒绝该模块子批次，累计失败 | 控制器按 watchdog 要求零目标，估计自然变旧 |
| 无限循环/超预算 | 外部 watchdog 拒绝批次、杀 worker | 其他机器人/物理继续，故障机器人安全状态 |
| 内存/磁盘/进程越界 | OS 强制拒绝或终止，标记 faulted | 不以 Host 崩溃代替失败处理 |
| 未授权消息/网络/文件访问 | 拒绝并审计；重复违规终止 | 不回显秘密资源存在性 |

共享 worker 崩溃后全部模块状态丢失；自动重启仅在模式允许、重试有上限时进行。Arena 可直接判定机器人失能，不允许通过无限重启获得额外预算。控制与显示的超时策略分别见 03/04，不把旧速度永久保留。

## Arena 权威与公平

服务器拥有地图/真实状态、命中、传感器模拟、能力/视图、时钟、提交顺序、部署摘要与评分；客户端只保有草稿、UI 布局、授权观测缓存和估计显示。比赛只运行服务器锁定 artifact，拒绝客户端上传“计算结果就是成绩”。

赛前固定 Core/SDK/物理/执行 profile、依赖镜像和资源配额；同场机器人使用同类硬件资源，记录抢占、负载和超时，必要时重赛。交换出生位置和使用成组隐藏种子降低偶然偏差；种子赛后按规则公布，活跃时不能泄漏。配额公平不是不同 CPU 绝对相同指令吞吐的承诺。

战斗无外部网络与赛中代码更新；观众延迟视图与参赛者数据分离；私有评分器与完整 Replay 只供审计。排行榜和公开回放属于后续产品功能，MVP 不建账号或排行榜服务。算法从合法观测推断敌人是允许的；跨进程读数据、未授权频道和泄漏全知回放属于违规。

## 替代方案、未决项与验收

嵌入 CPython、Python 线程、受限 builtins 和普通 subprocess 均不足以运行互联网不可信代码；容器轻量但共享内核风险更高；microVM 隔离更强但冷启动/内存成本更高。gVisor 兼容性和数学库性能需测试后决定，见 ADR-0013。

未决：浏览器严格网络隔离、桌面安全执行能力、服务器沙箱、真实内存/启动成本、侧信道风险接受范围。验收必须在目标部署上实际测试无限循环、内存炸弹、fork/线程风暴、恶意路径、Host/metadata 网络访问、跨机器人通信、畸形 JSON/日志洪泛、worker 强杀与 Host 连续运行；没有证据前不开放第三方服务器代码执行。

## M1 的实际本机边界

M1 为明确授权的**本人可信代码开发 profile**：原生 Rust Core 的私有管道只给 Host，CPython worker 是另一个进程，仅收到授权传感器和公开初始化数据。外部线程看门狗强制批次墙钟上限，超时强杀 worker；实时 tick 不 await 玩家程序。长度前缀在分配前限长、严格 JSON 深度限制、固定提交门和 Authority 校验都已实现；stdout 中的玩家 print 重定向到丢弃的 stderr，不能混入协议。

该 profile **没有** OS 文件/网络沙箱、硬 CPU/内存/进程配额，不接受第三方上传，也不提供 Arena。完整服务端隔离要求与 ADR-0013 仍有效且 Proposed；不能用本机死循环测试代替沙箱攻击测试。loopback HTTP 限定 Host/Origin、控制 token、POST JSON 大小和控制频率；这些是本地 UI Adapter 的保护，不代表可直接公开到互联网。M1 原范围仅有键盘来源；M1b 已支持启动时按执行器选择 keyboard/robot，并在程序故障时撤销目标。运行时动态控制权切换仍未实现。

## M2 实测浏览器 profile

双 origin / 双 Worker 已在 Linux Firefox 验证，Authority/玩家解释器不共享堆；Runtime 资源路由不提供配置、Core 或宿主源码。真实 Python JS 桥测试确认宿主句柄/文件不存在、UI/外网连接与嵌套 Worker 被阻止、fork 不可用；死循环强制终止后 Core 和 UI 继续。资源预算仍在 config/game.yaml：浏览器初始化 45 s，批次 20 ms，原生初始化仍为 5 s。

CSP 允许 Runtime origin 的固定只读资源请求，MEMFS 可写；浏览器无硬内存/磁盘/CPU 配额，未进行破坏性 OOM 压力测试，不保证抗所有 DoS。尚无第三方服务器代码执行或 Arena；ADR-0013 整体仍 Proposed，局部实现选择与成本由 ADR-0020 接受。详细攻击结果、来源与数据边界见 [16](16_BROWSER_RUNTIME.md) 和 [M2 报告](reports/M2_VALIDATION.md)。

## M3 测试与部署边界

Test/import/setup/玩家 unittest 也在独立 Runtime 中执行；原生仍仅可信本机代码，浏览器复用 M2 的独立 origin。候选不收到完整 Workspace 存储或 World，只收到固定源码与授权配置/传感器；其输出在 Test 中不会提交执行器。原子切换生成新 publisher 身份、清除旧提交队列/控制目标，旧 Worker 结果无法用于新租约。归档报告只供审计，不能恢复 Ready 授权。详见 [17](17_EDITOR_AND_DEPLOYMENT.md)。

## M5 当前增量

M5 每台机器人仍共享一个 Worker；每模块预算仅作准入，总批次硬预算与外部终止沿用原方案。模块之间不构成安全隔离，候选测试独立缓存不驱动实时执行器。图/连接/公开 Topic 均有 YAML 上限；见 [26](26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)。服务端 OS 沙箱仍待实现。
