# 静态资源归档、根入口与浏览器缓存清理验收

日期：2026-11-18。提交基线`307142c`；工作区已有设置/开发者显示等未提交修改，本轮保留并迁移其对应配置与Schema。没有提交、推送或手工操作日常userdata。设计见 [46](../46_STATIC_ASSETS_AND_ENTRYPOINT.md)、[ADR-0060](../adr/0060-static-assets-and-root-entrypoint.md)。

## 完成的迁移

| 原位置 | 当前位置/处理 |
| --- | --- |
| levels | assets/levels，十三关、稳定ID及前置不变 |
| templates及Host内嵌程序 | assets/templates；27段字符串提取，加上既有7份文件，统一common/weapons/navigation |
| config | assets/config，包括底盘、桌面、运行profile和Python准备锁 |
| docs/schemas | assets/schemas，29份Schema及索引 |
| docs/examples | assets/protocol/examples，规范样例及索引 |
| examples/robot | assets/examples/robot，独立SDK示例 |
| tools/tankbot.py | 根main.py直接执行原启动流程；旧文件删除，无链接或转发索引 |

协议实现`protocol/tankbot_protocol/`是编解码、校验及Transport代码，按用户确认保留。assets新增总索引、模板及协议说明；AGENTS明确今后静态资源规则。更新读取、Schema注册、依赖策略、部署环境摘要、基准源码/配置清单、Godot提示、开发工具和测试入口。历史报告只调整因迁移失效的本地链接，不重写当时的运行命令、数值和原始JSON。

具体路径见 [工作区文件清单](resource-layout-inventory.json)：其中包含任务开始前已有的设置/显示修改，不把它们全部算作本轮新开发。主要逻辑变更为main.py、Host的resources/配置/模板/环境读取、协议Validator、SDK依赖策略、工具/测试引用及文档检查器；资源按上表整体搬迁，历史Markdown只重定向本地资源链接。

`resources.repository_path()`把旧可信配置中的config/levels等引用映射到唯一assets文件，不保留双份配置；底盘/Runtime profile的目录限制继续执行。原绝对自定义配置/关卡目录可用。生成Core夹具只有`level_plugins.directory`位置变化，传入Rust的实际配置摘要相同。

## 源码、历史与行为保护

在迁移前冻结35个注册组件、十三关说明注入后的源码、starter Python及Core输入摘要。迁移后逐项相同，并保存为`tests/fixtures/resource-layout-before.json`回归基线。资源路径不决定生成目标，玩家工程文件名、模块API、模板版本、Workspace scope及存档格式保持；不会通过移动资源重新生成或覆盖玩家算法。

源码模板现在真正覆盖Weapons和Navigation；Hello Robot不要求写算法，使用common中的被动适配器。旧兼容组件仍保留。模板只以文本读取并由注册组件选择，不允许YAML导入任意脚本；路径逃逸拒绝。部署环境摘要会变化，旧Ready不能复用，但源码revision、ledger和历史不受影响。

## 缓存清理

先预览，再执行清理；完整清单在`.m1-cache/resource-layout-qa/cache-cleanup-preview.json`及`cache-cleanup.json`。删除1099个可重建目标，按文件大小统计共4,505,995,315字节，约4.20GiB，清单无遗留目标：

- node_modules：旧CodeMirror/esbuild等JavaScript依赖；当前游戏不使用。独立WASM对照只需系统Node。
- .tools/npm、build/web、build/browser：npm缓存、旧前端构建、Pyodide及其WASM/轮包。
- 219个旧Firefox测试profile中的页面、启动、编译及其他明确缓存；空web目录移除。

保留learning-browser-v1/v2/v3的HEAD/版本库、旧算法源码、所有测量日志/JSON/截图及历史报告；219个profile的idb等持久化存储仍在，不把潜在源码或运行证据按缓存盲删。原生Python/Godot、Rust工具链及独立WASM构建缓存保留。清理未创建新的生产自动删除机制。

## 实际验证

| 命令/验证 | 结果 |
| --- | --- |
| `python3 main.py --help` | 通过；无site-packages的帮助/参数错误也有回归 |
| `uv run --offline main.py --help` | 通过；与Python入口使用同一依赖准备逻辑 |
| 隔离`uv run --offline main.py`启动器烟测 | Godot/Host实际启动、窗口自动退出、本机API关闭均通过；记录`uv-launcher/result.json` |
| resource_layout定向回归 | 5项通过：全部源码摘要、Core、旧配置、安全路径、根入口与非内嵌模板 |
| python_env定向回归 | 10项通过：依赖准备、离线/失败重试、路径含空格、锁和隔离重启 |
| 两项导航配置拒绝定向测试 | 通过，验证自定义临时关卡目录继续有效 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 195项通过；`.m1-cache/godot-qa/20261118T145720927001/flow.json` |
| `python3 tools/check.py --suite godot --offline -- --disable-vsync` | 196项通过；`.m1-cache/godot-qa/20261118T145940893273/flow.json` |
| `python3 tools/check.py --suite wasm --offline` | 清理node_modules后仍通过原生/WASM武器、课程、轮电压、仓储/接触及JSON ABI对照 |
| `python3 tools/check.py --offline`（最终新进程） | 416项Python回归、18项Rust测试通过，退出码0；日志`standard-verified.log` |
| 文档/Schema/样例及生成配置一致性 | 169份Markdown、1485个本地链接、29份Schema、50个正例/25个结构拒绝例及JSON/Python片段通过；生成Core配置一致 |
| `git diff --check` | 通过 |

Godot流程使用新资源和main.py，继续验证保存文件→Start→独立检查/部署→通关/重试、改键/CAS、开发者选择、扫描、撤权及源码/ledger/revision/进度保留。F2使用隔离记录型编辑器启动器。窗口证据限Linux X11/OpenGL、Godot4.7.2、RTX5070 Laptop GPU、1440×900；生产VSync未改。

## 失败记录与限制

首轮统一检查`standard.log`因三处测试临时树未同步目录布局出现12项路径错误；已补assets父目录并使自定义关卡目录的写入与复制位置一致，定向重跑通过。中间进程`standard-final.log`仍持有修正前的两项测试定义，不能作为最终结果；最终新进程日志为`standard-verified.log`。全部日志保留在`.m1-cache/resource-layout-qa/`。

首轮C6 DWA/seed2还出现一次120秒关卡超时，结果记录行驶约5.46m、未停稳；未改参考算法、障碍、时限或Runtime截止。中间重跑两方法/三seed全过、周期超时数0，并保留`c6-intermediate-evidence.json`。观察到同seed准备后的正式起算tick不同（失败276、后次294），与既有准备时刻/传感器随机流语义有关，但本轮未证明这是唯一原因，不能据重跑成功宣称算法或整局可靠性保证。

最终新进程416项全量回归通过，包含上述三处修正及C6两方法/三seed；没有仅删除失败用例或只报告单项成功重跑。

未验证Windows/macOS、全部课程的正式GUI通关、独立发行包或长期可靠性。运行profile保持experimental。清理范围是本仓库可重建的浏览器缓存，保留的持久化浏览器数据和旧工程证据不是继续提供浏览器入口。
