# YAML 关卡插件迁移验收

## 范围与结论

2026-10-25，基线为提交 `ba2b5f8`。只迁移原有 C0–C4，正式目录仍有五个 YAML，没有开发新关卡或修改 Rust 物理实现。应用配置 1.9、关卡 Schema 1.0、现有协议/Topic/存档版本保持。架构、审计及迁移表见 [27](../27_LEVEL_PLUGIN_ARCHITECTURE.md)，编写流程见 [关卡指南](../../levels/README.md)，决策见 [ADR-0033](../adr/0033-declarative-level-plugins.md)。

实测环境：Linux x86_64、CPython 3.14.4、Rust 1.99.1、Node 22.22.1、Firefox 157.0.1、Pyodide 0.29.5。Accepted 只覆盖本文范围，不代表其他平台或未来组件已验证。

## 后续显示要求

用户在迁移完成后明确要求 Weapons 全章炮弹可见。C1–C4 的关卡内容版本升为 1.0.1，通过 YAML 开放并默认显示 projectiles；其他真值和算法权限不变。下文冻结基线与真实 UI 记录对应重构验收时的显示策略；原夹具保留，当前回归明确允许 world_effects 这一项后续变化，并验证四关实际开火时炮弹可见、敌车仍隐藏。具体决定见 [ADR-0022 修订](../adr/0022-campaign-capabilities-and-evaluation.md)。本次补充完整 Python 回归 152 项通过（85.859秒），相关前端设置/渲染测试共15项通过，生成夹具及文档检查通过。

## 旧架构与本次修改

原 `game.yaml` 已有集中数据，但关卡散布于 campaign、lesson、Radar profile、graph profile；模板、学习帮助、UI、CLI、Schema、进度排序及成功判定还有固定身份分支。现在通用模型/预算保留原文件，五个自包含 YAML 声明组合；安全加载器统一发现、验证、解析地图、编译内部兼容 DTO。没有关卡专属可执行插件或第二套手工配置。

`level_plugins.py` 负责发现、Schema/语义检查与适配；`level_rules.py` 负责组合/比较、进度和终局诊断；`level_templates.py` 选择注册脚手架并安全加入 YAML 说明字符串。既有 Authority、Campaign、Workspace、存档、UI 和 CLI 接入同一目录。浏览器启动器发布生成目录并复用相同 Python 模块，Core 只接收物理需要的 DTO，维持原消息大小限制。

Schema 顶层为 metadata、world、robots、communication、permissions、visualization、objectives、evaluation、randomization、tutorial、scaffolding。安全读取有字节、节点、深度和组件数量上限，拒绝别名、重复键、对象标签；校验组件、引用、端口、类型、预算、地图、指标与权限，错误返回 File/Path/Reason。只有地图允许引用 assets 内资源；不加载脚本或额外关卡配置。

## 五关保持的行为

| 关卡 | 配置 | 保持的行为与结果 |
| --- | --- | --- |
| C0 认识坦克与坐标 | [c0.yaml](../../levels/c0.yaml) | 人工驾驶、真值练习；移动/转向/命中清单；60秒首次操作起算 |
| C1 用 SE(3) 矩阵变换坐标 | [c1.yaml](../../levels/c1.yaml) | 理想 Radar、实际 NumPy 矩阵乘法、人工武器；估计并命中；60秒首次部署起算 |
| C2 噪声下跟踪 | [c2.yaml](../../levels/c2.yaml) | 带噪中心观测、差速巡逻、人工武器、双方3HP；120秒内存活击杀 |
| C3 让炮台自己瞄准 | [c3.yaml](../../levels/c3.yaml) | 三模块、程序角加速度/开火、无人工武器；120秒内存活自动击杀 |
| C4 从底盘中心推算装甲瞄准点 | [c4.yaml](../../levels/c4.yaml) | 中心观测、敌车姿态估计、四面装甲、非装甲吸弹；180秒内存活击杀 |

五关地图、玩家零初态、目标初态/路径、底盘、动力学、噪声及传感器结构保持。C1–C4 仍禁止驾驶，C3/C4 继续公开系统自身位姿。没有引入定位、scan 或建图课程。原诊断是位置/yaw RMSE 与采样/命中计数，无星级、加权评分或额外误差通关门槛；本次未增加。

## 基线与自动化结果

重构前保存 [冻结基线](../../tests/fixtures/level-behavior-before.json)，通过真实 Core/Authority 采集五关初始私有状态、公开 profile、100次 Radar 帧、合同/端口、模板文件集合、Runtime 初始配置、完整学习说明，以及成功/超时/死亡和诊断结果。新回归比较原字段，允许增加描述性元数据；未用迁移后的配置反向生成预期值。夹具中的旧包装源码只作兼容测试，不作为生产配置或注册来源。

| 验收项 | 测试证据 |
| --- | --- |
| A YAML 加载 | 发现并加载五个正式文件，与冻结目录比较 |
| B 严格校验 | 版本、字段、组件、重复 ID、未知目标、规则/指标、端口冲突、危险入口、覆盖算法文件、路径越界、缺失地图、权限及资源限额负例 |
| C 行为一致 | 五关冻结基线；原 Campaign、Weapons、时限/HP、传感器及物理回归；两种算法解法实际通关 |
| D 权限 | 程序有/无自身位姿 × UI 有/无位姿；禁止图层数据在 Authority 被移除；程序及测试输入裁剪；Node 普通 UI 图层上限 |
| E 切关 | C0→C1→C2→C3→C4→C0，新 run/world，旧 Worker/Core 结束，清空 Topic、观测和评分，源码保留 |
| F 重启 | 连续重载 C4，初态、时钟、估计/评分恢复；真实网页切换也重新建立 Worker |
| G 零代码扩展 | 临时目录创建任意 ID 的第六 YAML，修改初态、时限、命中阈值；自动发现、CLI、实际算法和进度均工作，无引擎修改；不加入正式目录 |
| H 玩家代码 | 重构前 C0–C2 包装逐字执行；既有 C1 变换、C2 跟踪、C3/C4 多模块解法在原生/浏览器正常 Test/Deploy；Workspace 非覆盖测试 |
| I 存档 | 旧 v1 存档逐字节保留，重开后完成/解锁状态相同；解锁取 prerequisites，不再解析 ID 数字 |

最终完整 Python 回归 **151项通过**（83.873秒），其中插件专项 **13项**。Rust **17项通过**。Node 显示12项、设置3项、类型提示2项、手柄7项，共 **24项通过**。原生/WASM 同工具链 ABI 对比覆盖两底盘各600 tick、巡逻1800 tick、角加速度/装甲600 tick，并验证非法操作及缓冲上限；未承诺跨平台位级一致。

已完成原生/编辑器构建、WASM release 构建及最终浏览器资源包准备。生成夹具检查和文档一致性检查通过；完整 Python 测试中的 loopback 网络测试需要沙箱外绑定本机临时端口。日志、截图和临时 Workspace 存于忽略的 `.m1-cache/`，未写入玩家 userdata。

## 真实网页回归

| 模式 | C0–C2 | C3–C4 |
| --- | --- | --- |
| 原生 Authority + Firefox UI | [原始记录](level-plugins-native-c0-c2.json) | [原始记录](level-plugins-native-c3-c4.json) |
| WASM + Pyodide + Firefox UI | [原始记录](level-plugins-wasm-c0-c2.json) | [原始记录](level-plugins-wasm-c3-c4.json) |

每关完成实际操作或 CodeMirror 保存→快照测试→部署→通关，检查固定视口、教学类型信息、源码保留和新 run。C3/C4 测试报告包含三个模块执行及六个授权仿真批次。测试用独立 Workspace/设置/存档和开发者直达功能，算法未获得额外真值权限。各记录对应当次构建；最终补充的显示拒绝组合由专项权限测试覆盖，不改变五关既有授权。

## 复现命令

在游戏专用 Python 环境或已安装 requirements 的环境运行：

```bash
python3 tools/build.py --offline
python3 tools/build.py --wasm --release --core-only --offline
python3 tools/prepare_browser.py --offline
PYTHONPATH=sdk/python .m1-cache/learning-venv/bin/python -m unittest discover -s tests -v
cargo test --locked --offline
node tests/test_rendering.mjs
node tests/test_settings.mjs
node tests/test_sdk_hints.mjs
node tests/test_gamepad.mjs
node tests/test_wasm.mjs
python3 tools/export_profile.py --check --offline
python3 docs/tools/check_design.py
git diff --check
```

浏览器回归沿用 tools/browser_m4.py、tools/browser_m5.py，具体 URL/浏览器端口可传参。复现时先启动独立 QA 服务及带 Marionette 的 Firefox；不要指向玩家正在使用的 Workspace。完整环境准备和离线缓存要求仍见根 README。

## 限制与后续编写流程

当前注册能力只覆盖已有五关：一个玩家、一个任务目标及现有传感器/规则/指标；更多机器人、机械臂、SLAM 等为 Planned。未实现独立静态 Web 分发、热加载、额外暂停 UI、跨 OS/其他浏览器实测或服务端强沙箱。浏览器场景包含客户端真值，权限是教学和接口隔离，不能对恶意客户端绝对保密。

添加复用现有组件的关卡：复制相近 YAML→设置稳定 ID/order/prerequisites→调整组合、教材及权限→运行校验/回归并刷新生成夹具→重启服务自动发现→用独立数据目录验收。无需新增初始化函数、UI/评分分支或手写注册项。新组件类型仍需通用引擎实现、Schema 和测试，本次没有提前实现未来能力。

## 实际修改文件

以下记录插件迁移与后续 Weapons 炮弹显示修订涉及的文件；之后的日志改进另见 [Python 测试日志验收](PYTHON_TEST_LOG_VALIDATION.md)。AGENTS.md、Rust 实现、SDK 公共消息及用户数据没有改写。

- [README.md](../../README.md)
- [config/game.yaml](../../config/game.yaml)
- [core/tests/fixtures/default-profile.json](../../core/tests/fixtures/default-profile.json)
- [docs/02_SYSTEM_ARCHITECTURE.md](../../docs/02_SYSTEM_ARCHITECTURE.md)
- [docs/04_STATE_AND_VIEW_MODEL.md](../../docs/04_STATE_AND_VIEW_MODEL.md)
- [docs/09_LEVEL_DESIGN.md](../../docs/09_LEVEL_DESIGN.md)
- [docs/10_DEVELOPMENT_ROADMAP.md](../../docs/10_DEVELOPMENT_ROADMAP.md)
- [docs/18_CAMPAIGN_DESIGN.md](../../docs/18_CAMPAIGN_DESIGN.md)
- [docs/25_ATTEMPT_RULES_AND_CONFIGURATION.md](../../docs/25_ATTEMPT_RULES_AND_CONFIGURATION.md)
- [docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md](../../docs/26_MODULE_GRAPH_AND_WEAPONS_CHAPTER.md)
- [docs/README.md](../../docs/README.md)
- [docs/adr/0022-campaign-capabilities-and-evaluation.md](../../docs/adr/0022-campaign-capabilities-and-evaluation.md)
- [docs/adr/0030-yaml-parameter-source.md](../../docs/adr/0030-yaml-parameter-source.md)
- [docs/adr/README.md](../../docs/adr/README.md)
- [docs/schemas/README.md](../../docs/schemas/README.md)
- [docs/schemas/campaign.schema.json](../../docs/schemas/campaign.schema.json)
- [docs/schemas/simulation-profile.schema.json](../../docs/schemas/simulation-profile.schema.json)
- [docs/tools/check_design.py](../../docs/tools/check_design.py)
- [host/tankbot_host/application.py](../../host/tankbot_host/application.py)
- [host/tankbot_host/authority.py](../../host/tankbot_host/authority.py)
- [host/tankbot_host/campaign.py](../../host/tankbot_host/campaign.py)
- [host/tankbot_host/campaign_templates.py](../../host/tankbot_host/campaign_templates.py)
- [host/tankbot_host/cli.py](../../host/tankbot_host/cli.py)
- [host/tankbot_host/configuration.py](../../host/tankbot_host/configuration.py)
- [host/tankbot_host/deployment.py](../../host/tankbot_host/deployment.py)
- [host/tankbot_host/learning.py](../../host/tankbot_host/learning.py)
- [host/tankbot_host/module_profile.py](../../host/tankbot_host/module_profile.py)
- [host/tankbot_host/view.py](../../host/tankbot_host/view.py)
- [host/tankbot_host/weapon_templates.py](../../host/tankbot_host/weapon_templates.py)
- [host/tankbot_host/workspace.py](../../host/tankbot_host/workspace.py)
- [runtime/browser_authority.py](../../runtime/browser_authority.py)
- [tests/test_campaign.py](../../tests/test_campaign.py)
- [tests/test_settings.mjs](../../tests/test_settings.mjs)
- [tests/test_weapons_m5.py](../../tests/test_weapons_m5.py)
- [tools/browser_m4.py](../../tools/browser_m4.py)
- [tools/browser_m5.py](../../tools/browser_m5.py)
- [tools/browser_template_upgrade.py](../../tools/browser_template_upgrade.py)
- [tools/export_profile.py](../../tools/export_profile.py)
- [web/app.js](../../web/app.js)
- [web/campaign-ui.js](../../web/campaign-ui.js)
- [web/visualization.js](../../web/visualization.js)
- [web/workspace-ui.js](../../web/workspace-ui.js)
- [docs/27_LEVEL_PLUGIN_ARCHITECTURE.md](../../docs/27_LEVEL_PLUGIN_ARCHITECTURE.md)
- [docs/adr/0033-declarative-level-plugins.md](../../docs/adr/0033-declarative-level-plugins.md)
- [docs/reports/LEVEL_PLUGINS_VALIDATION.md](../../docs/reports/LEVEL_PLUGINS_VALIDATION.md)
- [docs/reports/level-plugins-native-c0-c2.json](../../docs/reports/level-plugins-native-c0-c2.json)
- [docs/reports/level-plugins-native-c3-c4.json](../../docs/reports/level-plugins-native-c3-c4.json)
- [docs/reports/level-plugins-wasm-c0-c2.json](../../docs/reports/level-plugins-wasm-c0-c2.json)
- [docs/reports/level-plugins-wasm-c3-c4.json](../../docs/reports/level-plugins-wasm-c3-c4.json)
- [docs/schemas/level.schema.json](../../docs/schemas/level.schema.json)
- [host/tankbot_host/level_plugins.py](../../host/tankbot_host/level_plugins.py)
- [host/tankbot_host/level_rules.py](../../host/tankbot_host/level_rules.py)
- [host/tankbot_host/level_templates.py](../../host/tankbot_host/level_templates.py)
- [levels/README.md](../../levels/README.md)
- [levels/c0.yaml](../../levels/c0.yaml)
- [levels/c1.yaml](../../levels/c1.yaml)
- [levels/c2.yaml](../../levels/c2.yaml)
- [levels/c3.yaml](../../levels/c3.yaml)
- [levels/c4.yaml](../../levels/c4.yaml)
- [tests/fixtures/level-behavior-before.json](../../tests/fixtures/level-behavior-before.json)
- [tests/level_baseline_support.py](../../tests/level_baseline_support.py)
- [tests/test_level_plugins.py](../../tests/test_level_plugins.py)
