# 41 Runtime运行profile与整批截止

## 当前范围

当前唯一玩家Runtime是独立原生CPython，Godot只负责GUI。[ADR-0057](adr/0057-godot-only-player-entry.md)已删除Pyodide后端；本规范继续执行 [ADR-0053](adr/0053-backend-runtime-execution-profiles.md) 的预算拆分、尝试内冻结、完整解码截止及固定门。历史浏览器测量保留于报告，不表示当前仍有浏览器运行入口。

当前默认目录 `config/runtime-profiles.yaml`：模块声明准入总上限20ms；`native_local_v1`整批墙钟30ms，状态experimental。物理60Hz、算法dt、原始采样时刻、固定activation+6tick、权限和课程评分保持。玩家update自报耗时不是可信CPU配额，也没有逐模块硬隔离。

## 配置、冻结与兼容

`config/game.yaml` 的runtime.profiles_file只引用可信config目录；加载后展开为runtime.profiles。目录schema_version=1.0，共同声明上限独立于profile版本、backend、墙钟与状态。可信Worker工厂只选择native，Authority保存不可变有效profile，候选测试/部署继承，玩家请求/源码/遥测均不能改额。

旧runtime.batch_budget_ms单独存在时保持原义：准入与墙钟均等于该值；与profiles_file/profiles混用拒绝，不猜优先级。修改可信配置须新建尝试，不静默迁移玩家文件。

为读取旧2.1配置，Schema允许已弃用的browser字段和旧pyodide目录元数据；它们不参与执行。默认目录不发布pyodide，`select_execution_profile(..., 'pyodide')`明确拒绝，没有隐藏回退到浏览器。未知backend/ID、错误版本/数值、native默认后端不匹配仍拒绝。

```yaml
runtime:
  profiles_file: config/runtime-profiles.yaml
```

public_profile.runtime_execution_profile和timing.execution_profile公开ID、版本、实际参数、来源及摘要。timing.budget_ms只保留为墙钟诊断别名；模块准入只能读取module_declared_budget_cap_ms。

## 完整截止与固定提交门

| 时刻 | 含义 |
| --- | --- |
| started_monotonic_ns | Authority开始编码请求之前 |
| response_decode_started_monotonic_ns | 收完字节，开始严格JSON解码 |
| received_monotonic_ns | 完成接收/解码，可交付给Authority |
| commit_monotonic_ns | 固定门处理结果 |

deadline_ns = started_ns + batch_wall_deadline_ms × 10⁶。只有received_ns≤deadline_ns才及时，不增加epsilon宽限。范围包括编码、写入/排队、输入适配、update、输出构建/编码、回传和解码；解码中跨界同样失败，不取决于看门狗回调是否已调度。使用同一时钟域单调时间，不相减跨Worker绝对时间。

及时结果缓存到固定门，不能提前生效，也不能因门到来时已超过响应截止而误拒绝早已收到的结果。门到而没有合法结果时，已过墙钟记RESOURCE_LIMIT，否则记MISSED_DEADLINE；物理不能等待。宿主追赶可能用少于100ms现实时间推进6tick，扩大墙钟不能移动提交门。

原生单请求写线程避免管道阻塞Authority，外部看门狗终止失控进程组。重试/部署新建身份，旧Worker结果不能进入新租约；关闭清理与原有故障/制动策略保持。

## 一次性规划准备

Navigation C5/C6的5秒规划准备独立于周期profile和声明额度。从规划请求开始编码到完整结果解码，含规划器导入/构造、玩家膨胀/搜索/后处理及往返。解释器加载有独立初始化上限，不能把搜索挪到setup/reset规避预算。准备阶段无6tick输出门或执行器权限；路径验证/冻结后才初始化周期图，恢复30ms/6tick。合同见 [42](42_NAVIGATION_GLOBAL_PLANNING.md)。

## 耗时观测与基准

窗口观测提供批次/模块/编解码等p50/p95/p99/p99.9/max、profile和失败位置。可消费的有界事件流由基准保存JSONL分片，不以512批窗口冒充长测。每批先求模块update总和再计算分位数；不能相加模块p99或相减两个分位数推算通信开销。首次激活、稳态、缺失响应和截断样本分开记录，内部遥测仅作不可信墙钟诊断。

`tools/benchmark_runtime.py`和校准工具现在只执行native。参数取config/runtime-benchmark.yaml，支持空update、Weapons KF/EKF、Navigation四模块路径追踪、接近声明额度的受控负载及不返回update；隔离目录、源/配置/构建摘要、seed、正常/宿主负载条件和固定提交语义保持。near_cap先校准后冻结，不改变玩家时限。--plan只输出计划，--slice-attempts是短测，不作为完整尝试可靠性证据。

每片JSONL及汇总容量均受YAML限制；--resume验证身份，不覆盖旧格或混合不同源码。`tools/summarize_runtime_benchmark.py`可只读分析原有native/浏览器记录，不安装已删除的Pyodide资源；历史版本取原始元数据/报告，缺失信息不编造。

当前30ms依据历史原生候选测量，仍experimental。移除浏览器不构成新的尾部可靠性证明。至少报告实际批次、完整尝试失败率和统计不确定性；零失败或10000批都不自动证明整局失败率<1%。候选不满足时先分析队列、消息、验证和宿主追赶，不无限放宽预算。

## 历史双Runtime证据与当前验收

[2026-11-07报告](reports/RUNTIME_EXECUTION_PROFILES_VALIDATION_20261107.md)记录当时Linux原生及Firefox/Pyodide候选矩阵，包含历史40ms浏览器默认、失败和重跑；原始JSON不重写。浏览器量化的0ms不代表零成本，旧报告的适用范围保持，不能据此宣称当前有浏览器部署或竞技公平性。

当前回归覆盖原生整数截止/解码跨界、管道背压、死循环终止、尝试冻结、旧配置与退休后端拒绝、准入独立、固定门/追赶及遥测不扩额。标准检查和Godot玩家流程分组运行，WASM仅验证独立Core ABI。当前命令及移除范围见 [44](44_GODOT_DESKTOP_CLIENT.md)、[退役验收](reports/GODOT_ONLY_ENTRY_VALIDATION.md)。
