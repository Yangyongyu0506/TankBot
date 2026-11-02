# 仿真器模型、实例与场景重构验收

日期：2026-10-29；范围见 [32](../32_RESOLVED_SCENE_AND_COMPONENTS.md)，接受决策见 [ADR-0043](../adr/0043-resolved-simulator-components.md)。

## 完成内容

- 正式底盘 profile 2.0 集中质量、独立惯量、轮组、伺服、各向异性阻力、控制限制及外观；game.yaml 2.1 保留仿真/世界/平台配置。敌车使用自身模型，独立轮径标定与伺服限制能实际生效。
- 六关及自由试验场显式声明传感器实例，统一 Scheduler 管理创建、随机重置、固定 tick 采样、去重与关闭；原生样本与 Python 观测继续由原后端计算。原有 Topic、Schema、采样语义和玩家函数不变。
- ResolvedScene 的 world、robot、chassis、sensor 定义不可变；场景缓存复用定义，重试新建世界/Worker/run_id/估计/评分状态。字典仅保留为每实例的旧 Core/宿主适配数据。
- 地图覆盖及练习进度规则保留。未迁移玩家源码或改模板版本，没有写入正式 userdata 以执行验收。

## 自动化证据

| 检查 | 结果与实际覆盖 |
| --- | --- |
| Python 完整回归 | 201 项通过，最终一轮 143.011 秒；课程、权限、模板/历史保留、部署、切关、地图及进度 |
| 场景专项 | 4 项：2160 tick 基线、模型实际受力独立、不可变缓存/新 run、非法实例在 Core 前拒绝 |
| Rust | 18 项通过；包括既有接触、武器/装甲、紧凑模型和敌车路径 |
| 原生/WASM | 共享 JSON ABI 下 4200 个武器/课程/角加速度/装甲/小陀螺状态对比通过 |
| 配置与文档 | 生成 profile、Markdown 链接、Schema 正反夹具、Rust fmt 及 git diff --check 通过 |

`tests/fixtures/simulator-before.json` 在重构前从实际 Core 捕获六关×两底盘，每组 180 tick。重构后物理状态和 Radar/装甲观测的摘要逐项完全一致；新调度器还逐采样与旧独立 sample 接口比较。该结论限定同一构建/种子/输入，不承诺跨硬件位级一致。

模型隔离测试使用明确的测试向量修改两种底盘质量、惯量、轮径和伺服，检查玩家/敌车定义与实际初始受力响应；这些数字不是新的游戏默认值。场景测试确认同一对象重试不读取资产、不同 Authority 的物理/随机/配置状态独立，以及采样重复、逆时、reset/close 行为。

装甲 Rust 单元测试原先借用 C4 关卡的装甲开关；当前 C4 已按此前需求改为整车伤害，本轮改为在该测试中显式声明差速装甲组件。修复的是测试对课程的依赖，没有改变命中算法或伤害规则。

## 实际网页与证据位置

使用 tools/browser_m5.py、独立临时 settings/progress/store 和玩家权限，在原生与浏览器 WASM 两种模式分别执行 C3→C4→C5：打开编辑器、编辑多文件、保存、Test Ready、Deploy Active、回到游戏、人工/程序击杀并通关。两组均通过，浏览器实际执行 Pyodide Authority 与独立玩家 Worker。

本机证据目录为 `.m1-cache/scene-refactor/`：python-tests.log、rust-tests.log、wasm-tests.log、scene-tests.log，以及 native-ui.json、browser-ui.json 和各关编辑/运行 PNG。临时数据不作为运行时配置源，也不提交玩家私有项目或生成缓存。

## 限制

本轮保持中心对齐安装、30 Hz 原生观测及可整除周期；非零外参、同类多实例/多机器人、其他噪声与异频 IMU 窗口没有实现。原生 Core 的理想轮组不变，不是新增电机或轮地接触动力学。旧字典兼容层仍有每 run 的转换与有限复制，未声称完全移除所有配置字典。资源文件变更需要重新加载定义，不支持热替换冻结场景。未重新验证 Windows/macOS 或真实移动设备。
