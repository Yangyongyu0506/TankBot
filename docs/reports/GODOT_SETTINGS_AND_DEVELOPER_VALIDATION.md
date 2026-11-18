# Godot设置与开发者模式验收

日期：2026-11-18。提交基线`307142c`，开始时工作区干净。本轮没有提交、推送或操作日常`userdata/`。用户确认的范围为设置/F10、键位映射与恢复默认、玩家/开发者模式、独立图层和数据查看器，设计见 [ADR-0059](../adr/0059-godot-settings-and-developer-displays.md) 和 [22](../22_SETTINGS_MODES_AND_PROGRESS.md)。

## 实现与边界

- 设置使用固定视口内的遮罩面板，标题、关闭、保存和取消固定；键位和图层列表内部滚动。物理按键映射沿用设置YAML；重复键和组合键拒绝，Esc先取消捕获，恢复默认只修改草稿。关闭放弃草稿，保存走现有revision/CAS、文件锁与原子写入。模式切换要求先结束尝试并等待Start检查结束；打开设置不会暂停计时。
- 玩家图层遵循关卡`allowed_layers`、`user_toggleable`及默认显示策略。开发者可以自由选关，独立控制真实车体/目标、速度、碰撞外形、传感器、估计、轨迹、协方差、导航路径、检查点、地图网格和私有障碍等已有显示能力；这是固定组件集合，不是任意RViz插件系统。
- 开发者数据仅取现有受权`/api/developer`，进入独立缓存、插值及Sprite节点；敌车采用自己的`target_visuals`，Weapons.C4的敌车保持四向全向轮及实际小陀螺运动。开发者和普通显示使用相同仿真显示时刻，均不向未来外推。普通程序输入、PlayerViewSnapshot、物理及评分未改变。
- 只读数据查看器选择授权Topic或开发者诊断，限制显示字符数并保留阅读滚动位置。退出开发者模式先清空私有节点、数据与查看器；run和grant世代隔离迟到响应。设置轮询识别其他窗口的模式变化并重载。
- 普通定位、GPS和扫描历史有容量上限。扫描地图投影只采用同run/revision/source/frame、同原始sample tick的玩家EKF；没有匹配位姿时只显示车体系扫描。开发者真值也不能作为投影或玩家位姿的回退。

新增客户端参数集中在 [desktop-tools.yaml](../../assets/config/desktop-tools.yaml) 和对应Schema。没有新增依赖，没有更改管理API、SDK、机器人消息、玩家算法、模板、存档格式或Runtime预算。原生20ms模块声明额度、30ms实验性墙钟及固定6tick提交保持。

## 实际验证

| 命令 | 结果与范围 |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_desktop.py -v` | 15项通过；旧配置默认、资源/Schema及设置动作/图层与后端注册表一致 |
| `.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_application.py -v` | 7项通过；设置/进度、开发者权限不进入Python或普通视图等 |
| `.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_rendering.py -v` | 3项通过；物理不受显示参数影响、独立模型和敌车权限 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 最终172项通过；证据`.m1-cache/godot-qa/20261118T135333614545/flow.json` |
| `python3 tools/check.py --suite godot --offline -- --disable-vsync` | 最终172项通过；证据`.m1-cache/godot-qa/20261118T135720660644/flow.json`及下列截图 |
| `python3 tools/check.py --offline`（获准的沙箱外重跑） | 410项Python回归及18项Rust测试通过；文档/Schema/样例、生成Core配置一致性通过，退出码0；日志`standard-unsandboxed.log` |
| `python3 docs/tools/check_design.py` | 159份Markdown、1441个本地链接、29份Schema、50个正例、25个结构拒绝例及JSON/Python片段检查通过 |
| `git diff --check` | 通过 |

最终Godot流程包含真实Host API、F10和物理键捕获、YAML保存/重新读取、默认值取消/保存、陈旧revision拒绝并保留草稿、运行期间模式锁定、十三关目录解锁、Weapons.C4全向敌车与独立隐藏、Navigation.C6扫描/私有障碍、数据查看及撤权后的403/迟到响应拒绝。开发者预览不奖励完成记录，返回玩家原关卡后源码、ledger、历史revision仍可读取。原有隔离文件保存→Start自动检查/部署→Weapons.C0开火通关→重试及Navigation/Weapons往返流程继续通过。

窗口证据来自Linux X11/OpenGL、Godot4.7.2、NVIDIA RTX5070 Laptop GPU、1440×900。测试以Godot事件/控件和真实后端驱动，不是人工逐项点击验收。F2使用记录型编辑器启动器，不声称本轮人工使用了VS Code。隔离设置、进度、工作区、XDG目录和随机端口由测试工具创建。

## 截图

- [键位设置：捕获方向键与固定保存栏](assets/godot-settings/game-settings-keyboard.png)
- [独立图层选择](assets/godot-settings/game-settings-layers.png)
- [Weapons.C4：独立全向敌车、真实姿态与碰撞外形](assets/godot-settings/game-developer-weapons.png)
- [Navigation.C6：局部扫描与显式私有障碍图层](assets/godot-settings/game-developer-navigation.png)
- [开发者只读数据查看器](assets/godot-settings/game-developer-inspector.png)

## 失败记录与修正

保留`.m1-cache/settings-godot-qa/`中的首次失败和中间成功记录，没有只保留成功重跑：

1. 新局部观测画法曾使用重复变量名导致编译失败，改名后通过。
2. Godot解析JSON将设置`version: 1`变为浮点数，提交时被严格后端拒绝。客户端只对符合版本1的数值显式编码整数，未放宽后端Schema。
3. End后的同run旧状态轮询曾恢复“运行中”，阻止Navigation切换；新增状态世代拒绝旧响应，并立即采用End返回的权威状态。
4. 首次真实窗口虽然流程通过，但嵌入Window的自动最小尺寸把保存栏挤出视口。独立布局探针复现后，设置改为固定Control面板；新增保存栏边界断言，并重新完成无头和真实窗口172项回归。

统一标准检查首次在受限沙箱运行，410项中14项因创建HTTP/IPC/WebSocket的socket被拒绝而报`PermissionError: [Errno 1]`或无法bind。单项复现日志为`single-start-diagnosis.log`，首次全量日志为`standard-final.log`；随后以获准的沙箱外隔离检查重跑，410项全过，不以这些环境错误修改游戏行为。

## 限制与后续

本轮没有恢复曲线、算法实验台、工程备份管理、手柄、完整进度树或地图资产预览界面。未验证Windows/macOS、其他分辨率、全部十三关的正式GUI算法通关、长时间会话或独立发行包；未跑独立WASM对照，Core与其ABI未改。既有`--disable-vsync`只用于窗口验收，未修改生产VSync默认，也未解决历史默认VSync问题。没有通过本轮短流程升级30ms profile的experimental可靠性结论。普通CPython仍不是操作系统级强沙箱，开发者管理不是远程Arena授权。

## 文件范围

新增`clients/godot/{keyboard,display_policy,display_data,settings_dialog,inspector_dialog,developer_overlay,diagnostic_overlay}.gd`、`clients/godot/tests/{display_data_tests,settings_flow}.gd`，以及desktop-tools YAML/Schema、ADR-0059、本报告和截图。

修改Godot主界面、世界显示、时间线、主题和集成测试；`host/tankbot_host/desktop.py`、桌面配置/Schema、`tests/test_desktop.py`、`tools/test_godot.py`及文档检查器。同步根README、04/22/44规范、路线图、文档/ADR/Schema索引。未改Core、Authority、Supervisor、关卡YAML、日常源码或历史报告。
