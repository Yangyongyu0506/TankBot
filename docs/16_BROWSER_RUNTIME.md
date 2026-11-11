# 16 浏览器 Runtime 与平台适配

## 目的、范围与当前状态

当前浏览器模式复用原生Authority、SDK、课程、模块图和部署语义，已实现双Worker、固定资源的双origin启动器、受限快照及本机持久Workspace。M2建立此拓扑，历史证据见 [M2验收](reports/M2_VALIDATION.md)；当前后端profile与完整解码截止见 [41](41_RUNTIME_EXECUTION_PROFILES.md)、[Runtime验收](reports/RUNTIME_EXECUTION_PROFILES_VALIDATION_20261107.md)。仍是Linux/Firefox有运行证据的本机原型，不是Arena沙箱、独立静态网站或桌面发行包。

## C5一次性准备阶段

Robot Worker可先进入PreparationRunner，解释器就绪不等于周期控制就绪。可信init明确5秒规划截止；iframe对preparation请求使用该截止，后续step仍使用冻结的40ms profile。Core Worker/Authority用自身单调时钟完整解码后最终裁决，桥接耗时不授权宽限。规划器导入/构造/调用位于计时请求内，结果身份绑定run/deployment/task；Authority校验并交付静态路径后才构造周期模块。测试与正式候选各规划一次，关闭/旧Worker路由仍清理。详情见 [42](42_NAVIGATION_GLOBAL_PLANNING.md)，原有初始化上限与安全承诺不变。

## 进程与信任边界

```mermaid
flowchart LR
    UI[主线程 Canvas / 键盘] -->|控制请求| CW[可信 Core Worker]
    CW -->|授权 View / 公开 Profile| UI
    subgraph AuthorityOrigin[UI / Authority origin]
      CW --> A[Pyodide 内共享 Python Authority]
      A -->|私有 init / step JSON| R[Rust / Rapier WASM]
      A --> V[Validator / Selector / View Gateway]
    end
    subgraph RuntimeOrigin[无凭据 Runtime origin 的 iframe]
      F[可信桥与终止看门狗] --> PW[独立 Pyodide Robot Worker]
    end
    CW <-->|独立 MessagePort，仅序列化批次| F
```

`host/tankbot_host/authority.py` 增加可信的 `core_factory`、`worker_factory` 注入点。原生仍使用 `CoreAdapter` / `Supervisor`；浏览器使用 `runtime/browser_authority.py` 的 `WasmCore` / `BrowserSupervisor`。Authority、JSON Schema 注册、PSD/帧/时间/权限校验、Pose Selector 和 View Gateway 使用同一份 Python 源码，避免另写一套 JS 权限规则。

可信 Worker 因此也加载 Pyodide；物理仍完全运行在 Rust 内。代价是两个 Python 解释器、启动与 JSON 转换成本。当前测量可支持单机器人闭环；多机器人前需重新基准，不能用这一选择预设 Arena 的部署结构。决策见 [ADR-0020](adr/0020-shared-browser-authority.md)。

## 私有 Core ABI

`core/src/session.rs` 共享原生长度前缀 IPC 与 WASM 的操作分派。WASM 导出：

| 调用 | 约束 |
| --- | --- |
| `tankbot_input(size) -> pointer` | Rust 拥有输入槽；超过 1 MiB 返回 0；写入后才能 exchange |
| `tankbot_exchange() -> output_length` | 消费整个输入槽；返回 `{ok,data}` 或 `{ok:false,error}` 的 JSON 字节长度 |
| `tankbot_output() -> pointer` | 只读输出槽；下次调用失效；内存增长后必须重取 `memory.buffer` |

`web/wasm-core.js` 实现顺序调用、UTF-8 编解码和槽拷贝。每个可信 Worker 只有一个实例，不并发、不重入、不向 UI/Robot Worker 转移 WASM Memory。`init(config,chassis)`、`step(target,turret_target,fire_requests,revoke,revoke_turret)`、`snapshot` 的私有 DTO 不属于玩家协议；返回值含真值，仅 Authority 可以持有。错误路径返回结构化失败，不能把任意私有操作接到 UI RPC。

## Python 加载、时序与失败

`runtime/module_runner.py` 复用 CPython/Pyodide 的 Module 生命周期、传感器类型转换、输出收集与 Envelope 构造。玩家源码单独复制到 `/workspace`，不挂载宿主目录；只打包 `.py`，拒绝越界路径/符号链接和超长快照。M2 的启动种子路径继续只读；M3 的多文件编辑/部署和允许的 Manifest/Contract 文件见 [17](17_EDITOR_AND_DEPLOYMENT.md)。

Authority Worker 在每个固定边界调用同一 `advance()`：先提交上一批→采样→激活→裁剪视图→推进物理。60 Hz/4 子步、30 Hz 观测、10 Hz 算法和 6 tick 提交延迟保持原约定。Worker 的墙钟 timer 只负责调度，Python 响应绝不改变提交 tick。每次边界之间让出事件循环，不 await 玩家。

可信Worker工厂选择pyodide后端profile，Authority在尝试开始前冻结，并供测试、部署和实验Worker继承。声明总上限与往返墙钟独立；当前目录为20ms声明上限、40ms整批墙钟的experimental profile，权威参数见 [41](41_RUNTIME_EXECUTION_PROFILES.md)。Authority用自身整数单调时钟，从开始编码到完整响应接收/解码判断截止；恰好到期合法，解码期间跨界或迟到均拒绝，桥接elapsed_ms仅作诊断。

iframe在自己的时钟域执行局部timer和结果到达复核，超限 `Worker.terminate()`；timer调度延迟不能使迟到响应合法。早到结果缓存至activation+6tick，缺结果在原门丢弃并撤销程序目标；晚到、重复或旧worker_id响应不能恢复控制。宿主追赶时6tick未必有100ms现实时间，增加墙钟不移动门。浏览器后台降频和OS抖动不构成硬实时CPU配额，当前没有逐模块硬隔离。

初始化独立使用browser.startup_timeout_s（当前45s）；失败不开始世界时钟。候选在tick边界替换旧Runtime，最多两个玩家Worker；旧ready/fault也按worker_id隔离，不能启动或停止新Authority。候选失败保留当前世界，SDK/Authority修改后仍须重新prepare bundle。

## 资源、网络与数据权限

- UI origin 默认 `http://127.0.0.1:8765`，Runtime origin 默认 `http://127.0.0.1:8766`。Runtime 不设置 Cookie、不提供配置、Workspace、Authority bundle、Core WASM 或 API 路由。
- iframe 校验父 origin/source，仅绑定一次端口；Worker 只收到授权初始化/传感器和自己的 Python 源码。局部 UI 与 Sensor Envelope 仍走 Authority 既有权限路径。
- Robot Worker 响应头使用 `worker-src 'none'`、`connect-src 'self'`、`script-src 'self' 'wasm-unsafe-eval'`。允许读取自己的固定 Runtime 资源，阻止访问 UI origin、外网和嵌套 Worker；不是宣称绝对无网络。
- 固定 Pyodide **0.29.5**；Robot 使用 classic Worker + `importScripts`。本机 Firefox 的 module Worker 静态依赖图在严格策略下加载失败，classic 路径通过实测且保留限制。未来升级 Pyodide 必须重验 Worker 类型和 CSP，不能直接采用滚动 stable 示例。
- Worker 有自己的 MEMFS，可以写自己的文件；没有可靠的浏览器硬内存/磁盘额度。没有做破坏性内存耗尽压力测试，不保证浏览器进程可抵御所有 DoS，也不把 IndexedDB 当跨项目安全存储。
- 本地场景配置与 WASM 是设备所有者可检查的静态启动资源；只使用公开试验场，不把秘密 seed/地图放在浏览器部署中。Renderer 接口只收授权 DTO。远程隐藏世界必须留在服务器 Authority，不能照搬本地静态启动资源分发。

## 构建、配置与替代方案

`tools/prepare_browser.py` 校验 `config/browser-assets.lock.json` 的每个 SHA-256，首次下载固定文件，之后可 `--offline` 重建两份 bundle；不运行浏览器时联网安装包。底层资源和生成 bundle 放在忽略的 `build/browser/`，不提交第三方二进制。

当前应用配置为 `2.1`，浏览器接收同一加载器解析的场景与runtime.profiles目录，不接收可由玩家请求改写的预算。历史M2从1.3升为1.4引入browser段、M3在1.5加入workspace；这些是演进记录，不能代替当前配置。旧文件支持范围由加载器/Schema明确验证，工具不自动覆盖。Protocol仍为 `1.0` 未发布草案。

曾比较：JS 重写 Authority（少一个解释器但易发生权限/调度漂移）、把完整 Authority 移植 Rust（长期可评估，当前扩大重构范围）、仅做 Node WASM 探针（不能验证浏览器运行）。当前先以共享 Python 源码减少语义分叉，记录性能后再决定优化。

## 验收与开放项

验收：两底盘原生/WASM 各 600 tick 全快照对比；浏览器真实闭环、固定提交、程序武器、死循环终止后 tick/画面继续；同一 49 个协议夹具跨 Adapter；CSP/文件/宿主句柄负例；启动、内存分配和帧间隔报告。浏览器未实现的性能观察 API须标明，不能把 rAF 测量当所有 Long Task 的证明。

Windows/macOS与Chromium/WebKit尚无本轮核对到的完整玩家流程证据；CI定义不证明远程Runner已通过。NumPy课程白名单、本机多scope持久工程及备份已实现；独立Web存储、强OS沙箱、移动端、正式网络会话协商与Arena公平配额仍未完成。当前40ms默认依据Linux/Firefox候选对照，尚未证明整局截止失败率低于1%。

官方依据：[Pyodide 0.29.5 发布](https://github.com/pyodide/pyodide/releases/tag/0.29.5)、[Worker CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy)、[websockets 官方 API](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html)。这些来源用于接口研究，具体能力以上述锁定版本的实测为准。

UI origin提供带Host/Origin/token校验的管理API，Runtime origin无Workspace路由。源码持久化、备份与恢复由本机启动器提供，独立静态Web存储仍未验证；候选启动期间可信Core + Active + candidate共三个解释器。

## 玩家反馈与数学库增量

SDK 数值矩阵使用 NumPy，可信 Authority 和玩家 Worker 都加载已锁定的 NumPy 包。课程白名单在静态检查与玩家 loader 执行，不扩大传感器 grants，见 [23](23_PLAYER_CODE_AND_LIBRARIES.md)。玩家输出经受限 op: log 旁路、worker 身份检查和有界缓冲后进入管理状态；没有把日志写入物理快照或开放 Runtime 网络权限，见 [24](24_RUNTIME_LOGS.md)。

## 历史配置与证据适用范围

M2至Navigation C4初次验收曾使用20ms共享预算；原报告的测量、失败与配置保持原样。ADR-0053局部修订预算配置和截止计量，不修改既有固定tick、权限或课程评分。当前默认及其不确定性以41和11月7日报告为准，不能用旧20ms成功记录证明40ms的跨平台可靠性。
