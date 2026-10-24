# M4 本机教学闭环验收

## 范围与环境

2026-10-23，在 Linux x86_64、Rust 1.99.1、CPython 3.14.4、Node 22.22.1、Firefox 157.0.1 与锁定 Pyodide 0.29.5 上执行。验证 C0–C2、确认的 Radar/巡逻/血量模型、函数到类模板、非覆盖解锁、原生与浏览器 Edit/Test/Deploy、授权视图及击杀通关。参数权威为 [当前配置](../../config/m1.json) 与 [18](../18_CAMPAIGN_DESIGN.md)。

## 已执行的功能验收

最终回归：74 项 Python 测试、13 项 Rust 测试、10 项渲染测试通过；2×600 武器场景及 1800 帧巡逻场景的完整原生/WASM 私有快照一致。文档检查通过 54 份 Markdown、9 份 Schema、29 个正例及 25 个结构负例；领域语义另外由真实测试验证。

| 领域 | 实际检查 |
| --- | --- |
| C0 | 人工控制通路完成位移/转向/命中，系统自定位与真值练习图层 |
| C1 | 真实外部 Python/Pyodide 调用坐标函数，发布地图估计，玩家估计驱动瞄准并命中通关 |
| C2 | 指数平滑与三点滑动窗口均在原生闭环通过；真实 Firefox 编辑状态类、测试/部署并击杀 3 HP 巡逻敌车 |
| 动力学 | 同一受限力伺服、敌车独立差速/玩家全向组合、完整矩形巡逻；世界动量、偏心角冲与质量不增加 |
| 死亡 | 致命命中后移除敌车两个刚体、碰撞体及弹道障碍；已有弹丸/物理继续推进 |
| Radar | 遮挡/视场/量程、10 Hz、独立噪声/丢失统计、seed 复现、局部 ID、死亡后无回波 |
| 权限与时间 | C1/C2 无真实目标/弹丸/效果；Runtime 无敌车初态/路径；错估计不改世界、旧采样不覆盖新值、非法 PSD/权限/过期拒绝 |
| 生命周期 | 错误仅结束后发布、结束撤销控制/Runtime、每关新 run、源文件跨关保留、阶段模板 ledger 独立 |
| 显示 | 10 Hz 目标估计在 RAF 帧间插值、失效隐藏、相机保持固定世界朝向；桌面/窄窗口无网页滚动 |

真实 UI 原始证据：[浏览器](m4-browser.json)、[原生](m4-native-ui.json)。包含每关 run、通过 tick、HP、结束后 RMSE、测试部署 artifact、源码保留、视口尺寸与构建摘要。截图位于报告记录的 `.m1-cache/` 路径，不提交生成图片。结果针对所记录构建/机器；原生 CPython 和 Pyodide 的墙钟调度、编辑用时及噪声时序会使指标不同。

## 复现

```bash
python3 tools/build.py
python3 tools/build.py --wasm --release
python3 tools/prepare_browser.py --offline
cargo test --locked
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs
node tests/test_wasm.mjs
python3 docs/tools/check_design.py
```

真实 UI 使用临时编辑库启动 `tools/tankbot.py browser --level c0 --browser-qa --workspace-store PATH` 和启用 Marionette 的 Firefox，执行 `python3 tools/browser_m4.py`。原生改用 `serve --level c0 --workspace-store PATH`，执行 `python3 tools/browser_m4.py --url http://127.0.0.1:8765 --output docs/reports/m4-native-ui.json`。工具会编辑该库，必须使用临时目录；重跑时选择新的临时库以保持首次解锁路径。

浏览器 QA 桥仅在显式 `--browser-qa` 开启，返回普通授权视图与控制结果 JSON；不存在 World 或真值 dump。测试控制器仅读取该视图、玩家估计、自身位姿、炮台/武器状态和已知弹速；敌车真值仅用于可信评分和物理断言。

## 当前限制与下一步

Windows/macOS 和其他浏览器未在本次实机验证；CI 构建矩阵不构成平台支持证明。CPython 仍限本人可信本机代码；浏览器设备所有者可调试自己的 Core/启动资源，不能由本结果推导 Arena 安全。任务进度按会话保存；敌车只巡逻、不反击和避障，评分诊断覆盖整个尝试。

下一项为 M5a：完整多模块 Contract 图、稳定输入快照、逐批依赖与预算调度，先复用现有传感器和算法。新观测、定位 fix、scan、地图语义与模型仍需按后续任务单独确认。
