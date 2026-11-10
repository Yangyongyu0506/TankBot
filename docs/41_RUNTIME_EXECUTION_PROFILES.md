# 41 Runtime运行profile与整批截止

## 目的、边界与实施顺序

分离模块声明准入与Authority往返墙钟，按原生/浏览器测量选择默认。先完成兼容配置、冻结和计时，再做定向回归及基准工具；最后执行候选矩阵、统一回归并记录证据。原有两份2026-11-05评估保留历史，不覆盖或把30/50ms建议写成已验证结论。设计状态见 [ADR-0053](adr/0053-backend-runtime-execution-profiles.md)。

物理60Hz、算法dt、采样时刻、固定6tick门、评分、权限和玩家源码保持。每机器人仍共享Worker，update自报耗时不是CPU配额或模块硬隔离。

## 配置与兼容合同

config/game.yaml以runtime.profiles_file引用可信config/runtime-profiles.yaml；载入后展开为runtime.profiles，浏览器接收已解析目录。文件只描述运行约束，不包含玩家代码。目录schema_version=1.0，共同module_declared_budget_cap_ms独立于每个后端profile的profile_version、backend、batch_wall_deadline_ms、status。

原生/pyodide默认ID由目录显式指定，可信Worker工厂选择后端。Authority保存不可变有效profile，公开ID、版本、参数、来源和摘要；候选测试/部署继承，不能因修改草稿或收到遥测而改变。修改可信配置须新建尝试。

旧runtime.batch_budget_ms独立存在时保留原义：准入和往返都等于旧值。新目录和旧字段同时出现直接报错；不存在覆盖顺序，也不静默迁移玩家文件。缺少两种模式、未知后端/ID、错误版本/数值和目录后端不匹配均拒绝。

## 统一时间语义

| 时刻 | 含义 |
| --- | --- |
| started_monotonic_ns | Authority开始编码请求之前 |
| response_decode_started_monotonic_ns | 完整字节已收到，开始严格JSON解码 |
| received_monotonic_ns | Authority完整接收/解码并可交付的时刻 |
| commit_monotonic_ns | 固定门处理结果的时刻 |

deadline_ns = started_ns + batch_wall_deadline_ms × 10⁶；received_ns ≤ deadline_ns才及时，不添加epsilon宽限。检查范围包含编码、写入/排队、输入适配、update、输出构建与编码、回传及解码。响应在解码中跨界同样终止，不因看门狗尚未调度而接受。只在同一时钟域计算差值；不同Worker的绝对时间戳不能互减。

及时响应可以缓存到固定门，不能因提交时墙钟已晚于响应期限而错误拒绝；早到不能提前生效。到了门仍无合法结果时，若墙钟已超限记RESOURCE_LIMIT，否则记MISSED_DEADLINE；不能等到放宽的墙钟上限。宿主追赶可能在不足100ms现实时间推进6tick，这不是新增等待权。重试新run/Worker身份，关闭后迟到消息不进入新租约。

原生编码之后通过单请求写线程发送，管道阻塞不阻塞物理；外部看门狗可终止进程组。浏览器Core Worker独立复核最终完成时间，iframe使用自身单调时钟执行局部看门狗并检查迟到；旧worker_id消息被丢弃。启动仍用单独启动上限。

## 观测与隔离基准

UI有界窗口保留p50/p95/p99/p99.9/max、阶段、profile及失败位置。另有可消费的有界事件流，基准及时落JSONL分片并明确丢失/截断，不依赖512批或最近32条。日志只保存计时、身份/摘要和必要状态，不复制真值、传感器或普通用户项目。

同一批模块update求和后再算分位数；不能相加模块p99，也不相减两个分位数推断通信开销。首次正式激活不丢弃，冷启动与稳态分组；浏览器0ms表示量化范围，不是零成本。内部遥测始终标记不可信墙钟。

基准使用隔离设置/存档/Workspace/端口/浏览器目录，固定构建、源代码、seed和场景。覆盖空update、Weapons C2 KF、C3 EKF、Navigation C4四模块、接近20ms声明额度的受控计算和不返回update。先80ms诊断观察尾部，同时保留提交门；再实际运行原生20/30、浏览器20/30/40/50各候选。正常与可重复宿主负载分开记录，每个主要工作负载每后端至少10000批；汇总必须列各条件样本、重复、失败，不能只留成功重试。

## 默认选择与验收

已以20ms为基线完成实际候选对照；当前原生/浏览器分别使用native_local_v1、browser_pyodide_v1，整批墙钟分别为30ms/40ms，声明总上限均为20ms。两类profile均保持experimental，见 [实际验收](reports/RUNTIME_EXECUTION_PROFILES_VALIDATION_20261107.md)。若数据不足以证明整局截止失败率<1%，profile仍为experimental，不称可靠性保证。至少报告尝试级失败率及统计上界；10000批不是自动达标。候选都失败时先分析排队/同步消息/验证/追赶，不无限增加时限。

验收包括配置兼容与冲突、尝试内冻结、准入独立、整数截止/解码跨界、迟到/重复、死循环/旧Worker关闭、受控/追赶、遥测不能扩额；执行统一检查、WASM和实际网页。基准原始记录、机器可读汇总、平台范围与未完成项将在本轮报告列明；没有实测的数据不填造。

## 运行入口与字段示例

```yaml
runtime:
  profiles_file: config/runtime-profiles.yaml
```

已解析配置使用runtime.profiles，不再携带profiles_file。旧batch_budget_ms独立模式仍可加载；与profiles_file/profiles同时出现均报RUNTIME_PROFILE_CONFLICT，即使数字相同也不猜优先级。

public_profile.runtime_execution_profile及timing.execution_profile公开profile_id、profile_version、backend、声明上限、墙钟、status、source和sha256。timing.budget_ms保留为墙钟诊断别名；准入只能读取冻结profile.module_declared_budget_cap_ms。未解码迟到字节只记录response_arrival_ms并标censored，不计入完整round_trip分布；gate_wait_ms是收到至提交的合并观察，包含门等待与Authority校验，未声称两段已单独分解。

长测工具为tools/benchmark_runtime.py，参数由config/runtime-benchmark.yaml经runtime-benchmark.schema校验。near_cap必须先运行tools/calibrate_runtime_benchmark.py，并将冻结的calibration.json传入--calibration-file；校准仅调整测试循环次数，从不调整玩家时限。--plan不启动浏览器，--slice-attempts明确为短测。已完成格可用--resume复用，同一源码/场景身份不匹配时拒绝；中断格保留原分片，不静默追加或覆盖。

JSONL每片至多8MiB、每格至多128片，汇总至多100000批，事件队列512条；这些配额均来自YAML。读取/落盘不足会显式报告丢失或停止，不能以旧窗口冒充长测。tools/summarize_runtime_benchmark.py按逐批事件重建同批update总和、冷启动准备/首次激活/稳态、阶段分位数、截断、课程终局和因Runtime中止的实验，输出仅含计时、摘要及获授权终局指标。

完整矩阵与最终版补测按源码分组，不能混合提高置信度。10,000批门槛按每后端/主要负载的全部候选与条件累计；辅助空批、near_cap、死循环另列实际数量。Headless前台可见Runtime页保留正式调度/消息但不画游戏画布，完整UI的编辑/部署/通关须另附证据。Linux/Firefox结果不外推其他平台、后台调度、OS沙箱或Arena公平性。
