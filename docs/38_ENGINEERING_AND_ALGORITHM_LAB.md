# 38 工程检查、算法实验台与项目保留

## 目的、范围与实施顺序

依据2026-11-04评估和当前源码，按以下验证边界推进：统一检查入口→Weapons C2固定输入实验→原生/Pyodide耗时诊断→项目备份/保留→局部职责提取→当前文档及未来课程建议。评估原文保留于 [原报告](reports/PROJECT_REVIEW_20261104.md)，本轮结果独立记录，不把历史实测当作新证据。

本文首轮交付不新增关卡或物理；当时十关、20ms墙钟、6tick提交及玩家源码保持。后续Navigation C4已增加为十一关；当前墙钟与声明准入的独立profile修订见 [41](41_RUNTIME_EXECUTION_PROFILES.md)，本文实验权限和源码保留合同继续有效。新增工程配额集中于 [engineering.yaml](../config/engineering.yaml)，经过 [Schema](schemas/engineering.schema.json) 校验；课程授权仍来自YAML。架构取舍见 [ADR-0051](adr/0051-engineering-experiments-and-retention.md)。

## 本地和CI检查合同

`python3 tools/check.py` 依次执行自动发现的普通Node组件测试、Python回归、Rust、文档及生成profile核对，任一失败返回非零。`--suite frontend/python/wasm/browser` 可单独选择；`--offline` 复用已准备依赖。正常Cargo与仓库本机工具链选择复用build.py，不另维护一套路径。

`npm test` 递归发现test_*.mjs，排除需构建产物的test_wasm.mjs；新组件无需修改CI清单。`npm run test:wasm` 单独验证已构建原生/WASM的语义一致性。`npm run test:browser -- --mode both --offline` 创建隔离的课程工程、前置存档和Firefox，执行真实网页流程并清理专用进程；不操作日常userdata。前置通关记录是夹具，不声称本轮重新通关旧课程。

CI构建矩阵与Linux回归使用这些相同入口。构建通过只证明构建/静态组件或协议结果；真实玩家流程、操作系统、浏览器和安全支持范围必须另附运行证据。普通检查不下载Pyodide，也不偷偷把网页检查当作已执行。

## 最小实验：单模块目标滤波

首版只开放 [Weapons C2](../levels/weapons.C2.yaml) 声明的target_filter_replay组件。evaluation.experiment明确声明输入Topic、输出类型、误差反馈和可选诊断长度；加载器拒绝执行器、模块图、未授权输入/目标图层/误差指标。UI入口来自catalogue能力，不按ID分支。

1. 正式部署后，玩家点击“算法实验台→开始录制”。只捕获已冻结、已提交给普通Runtime的授权请求，不复制World或开发者DTO。
2. 记录有界批数/字节数、原始测量、源revision与源码、配置摘要、seed、物理频率、录制/尝试/部署tick、Core摘要、Python/平台和依赖版本。达到容量停止并说明原因；运行失败保留日志和失败tick。
3. 停止录制并结束当前尝试，选择A/B两个保存版本。在独立Worker中依次重置并回放相同请求；输入摘要相同，源revision/环境摘要不同，各自输出不进入物理、正式画面、计分或进度。
4. 显示实际执行批数、原始r/θ、地图系估计、可选协方差、采样误差、累计/分段RMSE、缺测区间、异常栈和失败位置。未发布协方差/尚无估计时显示缺失，不补零。
5. 可保存、导出和重新导入复现记录。导出含源码与授权输入、比较结果和日志；引用的revision参与历史保护。每个比较版本可另行导出源码，通过F2既有导入预览恢复，不自动覆盖当前工程。

私有目标参考只保留在Authority侧会话内，用采样tick对齐评价。YAML显式允许sample_error_m/cumulative_rmse_m/segment_rmse_m，且现有目标估计/误差显示权限必须同时成立。真值坐标、速度、巡逻状态和评估句柄不进入普通玩家Worker或导出文件。重新导入后仍可复现输出/错误；没有原会话私有参考时，新RMSE留空，不用测量冒充真值，也不沿用旧版本的分数。

准备时间和部署时刻影响传感器随机流的位置，因此记录这些时刻，比较时不重新采样。实验重置算法，并为Python random/NumPy设置记录seed；不恢复原部署中途的内部状态，不保证有系统非确定性行为的算法可逐位复现。不同平台/库/浮点目标需核对环境摘要。

这里的NumPy设置作用于全局np.random状态，不能替无参default_rng()或玩家自行创建的随机源指定seed。使用独立Generator的算法应在自身配置中明确种子；玩家单元测试产生的导入副作用也不属于可恢复的中途算法状态。

### 可选算法内部诊断

```python
from tankbot import diagnostic
import numpy as np
from numpy.typing import NDArray

innovation: NDArray[np.float64] = np.array([0.1, -0.2], dtype=np.float64)
# 仅在update内部且本关显式授权时调用；不要求滤波器必须计算创新。
diagnostic("innovation", innovation)
```

也可通过ModuleContext.diagnostic调用。名称和元素数由关卡授权；每批事件数、有限实数/维度、总线消息大小均受限。未授权、NaN/Inf、错误维度或超额明确报错；Authority再次校验，不把SDK检查当权限边界。C2开放innovation(2)、innovation_covariance(4)、nis(1)；不限制玩家采用某种滤波算法。

### 三类“通过”不能混用

| 操作 | 可得出的结论 | 不能据此宣称 |
| --- | --- | --- |
| 测试快照 | 语法、导入、接口、单元样例与6批短输入检查通过 | 算法效果合格、正式通关 |
| 固定输入回放 | 两个滤波版本在相同测量上的输出和错误可对照 | 控制器的新闭环结果 |
| 完整场景重跑 | 从声明的初态、seed和启动时刻重新驱动物理并评价 | 任意地图/硬件均有效 |

首版UI拒绝控制器回放和含执行器的实验。后续控制比较必须独立重建场景、固定启动时序，并记录输出如何改变后续观测；旧传感器记录不能充当新控制器的世界。未来多模块/控制实验不因本接口存在而被视为已实现。

## 耗时观测与边界

RuntimeTiming在现有Supervisor与浏览器Adapter上增量观测。每批记录输入采样tick、激活/固定提交tick、宿主单调时钟的启动/接收/提交时刻，以及模块解码、update、输出构建；序列化、写入、往返和收到后等待提交门分别记录。Native和Pyodide共用MeasuredExecution。

输出编码无法把自身最终耗时放进同一已编码消息，因此报告前一批编码耗时，并附前批step_id；UI明确标“前批”。浏览器桥接与Authority总往返是不同计时范围，不能互减或假定跨Worker绝对时钟同步。通信/排队/调度的剩余时间没有被可靠分开的部分明确保留为往返，不伪造独立CPU耗时。

有界窗口提供p50/p95/p99/p99.9/max、超时率和最近失败位置，并公开冻结profile。可消费的有界逐批事件流供长测落盘，丢失计数显式报告，不用窗口冒充完整样本。Worker内部数值属于可伪造的诊断；宿主墙钟仍执行现有预算。探针在协议校验之前读取响应，遇到非法telemetry只忽略该诊断字段，正式校验照常拒绝，不能导致读线程崩溃。观测不改变冻结profile或失败处理，不放行错过门的结果，也不把update墙钟当CPU配额。实验标记为replay_validated，不冒充物理committed；回放等待门使用独立计数器。先依据实测决定是否优化，不在本轮更换编码或重写Authority。

## 项目备份、保留与恢复

F2→模板、备份与恢复→“项目容量与完整备份”，区分当前HEAD、历史快照、测试/部署归档、实验记录、压缩备份和恢复区。这里是当前课程项目，不包含进度和设置；完整个人备份仍应另外保存userdata。

所有维护操作复用原Store文件锁。固定版本显式写入PINS；历史清理先预览保留原因，保护HEAD、固定项、近期版本、部署/测试、归档/实验及模板计划引用。归档默认全部保留，用户可逐项选择回收。清理应用同时检查revision CAS及目录/引用指纹，过期预览拒绝执行。

确认清理时先写有摘要的gzip备份，再写prepared恢复日志并移动文件，最后标记complete。中断后在锁内回滚已移动项，不替换HEAD。恢复区仍占容量；显式清空前验证压缩备份包含所有待移除副本，之后仍可从该备份恢复。不会自动清除历史或悄悄扩大磁盘配额。

备份导入先验证摘要、文件路径、快照内容、引用和总量，并预览源码差异。应用前保存当前完整备份，导入缺失不可变对象，最后调用原子HEAD发布；原版本仍在历史或压缩备份中。异常中断允许留下已验证的额外历史对象，不能把HEAD指向半成品。软链接、路径逃逸、无效恢复日志和冲突拒绝。原迁移函数继续复制备份/固定项/恢复区，不合并另一个课程的源码。

导出会从必要的旧压缩备份取回已清空恢复区的数据，使单份导出能在另一台机器恢复；不递归嵌套全部旧备份。导入后恢复区引用绑定导入包的摘要。旧压缩备份也有单独的预览/确认清理，最新备份和仍被恢复区引用的备份禁止删除；未选择的备份保持原样。

## 管理接口与兼容

| 接口 | 语义 |
| --- | --- |
| /api/experiment/{status,start,stop,export,clear} | 本关实验状态、显式录制与导出 |
| /api/experiment/compare | 原生传revision由宿主读库；浏览器传已读snapshot到Core Worker，二者都校验快照 |
| /api/experiment/import | 仅导入授权记录，不自动运行或覆盖源码 |
| /api/workspace/revisions、storage、pin | 元信息、总量和固定版本 |
| /api/workspace/backup_export、backup_preview、backup_apply | 完整备份、显式预览与CAS恢复 |
| /api/workspace/backup_cleanup_plan、backup_cleanup_apply | 预览并显式移除无必要引用的旧压缩备份 |
| /api/workspace/cleanup_plan、cleanup_apply | 可恢复清理计划和确认执行 |
| /api/workspace/recovery_restore、recovery_purge | 显式恢复或清空已备份副本 |
| /api/workspace/experiment_save、experiment_list、experiment_load | 持久化复现记录，不奖正式成绩 |

原生沿用Host/Origin/control-token校验，浏览器实验执行只在Core/Robot Worker，启动器仅保存文件；Runtime origin不服务管理接口。完整备份预览有单独的总量上限，其他API保留原消息上限。协议只为runtime_step_result增加可选telemetry；旧消息仍合法，SDK算法函数签名不变。公共结构见schemas中的engineering、experiment及experiment-package，端到端结果见 [本轮验收](reports/ENGINEERING_QUALITY_VALIDATION_20261105.md)。

## 局部组织调整与后续限制

runtime_profile只装配课程公开初始参数；Authority继续拥有物理/授权/时序。management只共享静态资源和纯分发，两个Transport的CSRF、CSP和源隔离不合并。messages统一SDK发布类型与Runtime解码，正式JSON Schema仍是独立契约。两个航点脚手架移到templates/navigation，生成字节保持一致，其余脚手架后续逐个迁移，不整体重写。

首版不包含通用实验编排、远程代码托管、竞技评分、多模块回放、图形化创新矩阵编辑或跨平台性能承诺。后续课程建议见 [39](39_NAVIGATION_COURSE_PROPOSALS.md)，新增模型和评分参数仍须确认。
