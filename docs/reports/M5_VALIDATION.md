# M5 多模块与 Weapons 验收

## 范围、环境与结论

2026-10-25，Linux x86_64、Rust 1.99.1、CPython 3.14.4、Node 22.22.1、Firefox 157.0.1、Pyodide 0.29.5。本机完成用户修订后的 M5：多模块运行图、Hello Robot / Weapons 章节、C3 自动瞄准、C4 敌车 x/y/yaw 与有效装甲。参数版本 1.8，来源 [game.yaml](../../config/game.yaml)；规范见 [26](../26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)。自身定位课程、scan、建图并未实现，已移至后续章节。

## 自动化与真实 UI 证据

129 项 Python 测试（126 项全量回归加 3 项图边界验证）、17 项 Rust 测试、24 项 Node 行为测试通过。原生/WASM 对比覆盖两种底盘各 600 tick、巡逻场景 1800 tick、角加速度/装甲场景 600 tick 的完整私有快照；同工具链实测相等，不承诺跨硬件位级一致。

| 领域 | 验证行为 |
| --- | --- |
| 图准入 | 类型、发布/订阅权限、单写者、重复端口、未知输入、setup 依赖环、预算、异步拒绝 |
| 时钟 | 冻结输入、跨批次可见、采样 tick 保留、event 新序号触发、缺输入 dt 累积、实际激活 origin reset |
| 失败与部署 | 普通错误只拒绝该模块输出，连续失败停止；失败候选保留 Active；整图回滚重建、物理不回滚 |
| 课程控制 | C1–C4 拒绝驾驶；C3/C4 人工炮台/开火被拒；自身位姿仍为系统；C4 旋转敌车不改变理想中心观测 |
| 物理 | 加速度力矩饱和与反向耦合、零 α 仅轴承阻力、准确 watchdog、速率保护不改速度；旋转/移动装甲首次接触、非装甲吸弹、角冲与质量不增加 |
| 数据 | TargetPose 的 frame/新鲜度/PSD、NumPy shape/只读、空点云；目标 yaw 仅从玩家估计读取，跨 ±π 插值 |
| 迁移 | C2→C3→C4 非覆盖算法，C3/C4 合同类型变化会提示升级，模板版本 2.0.0，旧源码 revision 保留 |
| UI | 原生与浏览器实际 CodeMirror 写入、保存、Test/Deploy、全部三模块执行、模块页、估计 yaw/装甲、C3/C4 通关、固定视口 |

真实 UI 原始记录：[原生](m5-native-browser.json)、[浏览器 WASM/Pyodide](m5-wasm-browser.json)。每个测试快照运行 3 项系统 unittest 和 6 个授权仿真批次，报告均列出 aiming/coordinates/tracking 已执行、无等待模块。独立临时 Workspace、设置和存档未修改玩家项目；使用开发者模式仅便于直达关卡，算法输入仍按课程授权。截图路径记录于 JSON，生成图片不入库。

## 数值算法可达性与噪声测量

`tests/weapons_support.py` 仅为验收参考，不是给玩家自动填好的答案。两种方案分别使用常速度 Kalman 与有限滑动窗口回归，只读取授权观测及公开安装；控制器参数取 YAML，不读取敌车路径/真值。玩家默认算法保留 TODO。

| 关卡 / 方法 | 通过 tick（起点 0，60 Hz） | 我方剩余 HP | 目标物理命中数 | XY RMSE / m |
| --- | --- | --- | --- | --- |
| C3 / Kalman | 224 | 3 | 3 | 0.393 |
| C3 / Window | 305 | 3 | 3 | 0.435 |
| C4 / Kalman | 793 | 3 | 7 | 0.272 |
| C4 / Window | 556 | 2 | 4 | 0.361 |

C4 都由 3 次装甲有效伤害击杀，其他物理命中不扣血；Window 方案发生一次合法自伤。C4 yaw RMSE 分别约 0.896 / 1.087 rad，包含中心观测不可观的原地转向；通关说明任务可达，不证明持续高精度姿态估计。运行中不返回这些真值诊断。真实网页编辑/部署时间不同，噪声序列所处 tick 和指标也不同，不要求复现相同击杀 tick。

合成 4 m 静止中心、无墙、1 万次 Radar 采样：8992 次有效检测，丢失 10.08%；实测 σr=0.44710 m、σθ=0.08038 rad。将点转换到地图后，58.91% 落在 0.8×0.6 m 车体矩形之外。统计符合确认的 0.45/0.08/10%，并证明测量散布超出车体；不能推断任意距离或任意样本都在车外。原始数据汇总见 [数值记录](m5-model-validation.json)。

## 复现

```bash
python3 tools/build.py --offline
python3 tools/build.py --wasm --release --core-only --offline
python3 tools/prepare_browser.py --offline
cargo test --locked --offline
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs
node tests/test_settings.mjs
node tests/test_sdk_hints.mjs
node tests/test_gamepad.mjs
node tests/test_wasm.mjs
python3 docs/tools/check_design.py
python3 tools/export_profile.py --check --offline
git diff --check
```

Python 测试工具使用已具备 requirements 的解释器，本机为 `.m1-cache/learning-venv/bin/python`。UI 工具 `tools/browser_m5.py` 通过专用 Firefox Marionette（默认端口 2831），要求独立存档的服务初始为 C3、开发者模式；可用 `--url`、`--port`、`--output` 配置。浏览器服务加 `--browser-qa`，`?runtime=browser`；先准备 Pyodide 资源。不要对玩家现用 Workspace 执行该编辑验收。

## 验收中修复与剩余边界

修复 C3→C4 时“已有多模块就兼容”的错误判断；按输入输出 Schema 检查课程脚手架，升级保留算法。角加速度频道使用专用 cmd_accel Schema 约束，旧 cmd_vel 保持语义。新增配置检查章节顺序、装甲模式和执行器 grant 一致性。

尚未验证其他 OS/浏览器、实体手柄和大规模多 seed 难度曲线；未实现服务端 OS 沙箱、每模块独立抢占、独立浏览器存储、完整 Lab/Arena。共享 Worker 为机器人故障域，物理独立推进。下一项建议为 Locomotion 首关的任务与接口确认，不自动开始新增物理模型。
