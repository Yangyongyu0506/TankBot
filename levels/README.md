# Level Plugins

本目录的五个 YAML 是现有关卡的唯一关卡配置源；没有新增正式关卡。正式 Schema 为 [level.schema.json](../docs/schemas/level.schema.json)，架构和迁移说明见 [27](../docs/27_LEVEL_PLUGIN_ARCHITECTURE.md)。

## 编写与验证流程

1. 选择使用相同现有组件的配置作为起点，完整保留所需字段。metadata.id 使用新的稳定 ID，order 唯一，prerequisites 只引用已发现且排在前面的关卡；不要修改现有 c0–c4 ID。
2. 在同一 YAML 中声明地图/初态/传感器/控制源、通信合同、权限、规则、诊断、教材与模板。地图可 inline，或仅引用 assets/ 内 `{walls: [...]}` 格式的地图文件；禁止 include 其他配置或脚本。
3. 机器人、传感器、规则、指标、可视化及模板必须使用已登记类型。调节现有参数不需要改引擎；未登记能力明确报错。当前仅一个玩家和一个目标，不提前宣称支持 SLAM、机械臂或多机器人课程。
4. 先设置程序 inputs/outputs/actuators，再分别设置 View Policy 与 allowed_layers；初始显示和可切换项必须在显示权限内。默认保持旧用户图层偏好；需要按新关卡初始状态显示时可设 preserve_user_settings=false。
5. objectives.success 用 compare/all/any/not，终局数组顺序就是优先级。沿用声明的 timer_start；诊断仅结束后发布。不要通过改变显示权限改变评分。
6. 玩家算法文件不得加入 runtime.managed_files。YAML 只能选择引擎模板并提供字符串说明，不能提供执行脚本。默认入口、合同路径、类型、连线、预算和依赖均会校验。
7. 运行 `python3 docs/tools/check_design.py`、相关自动测试，以及 `python3 tools/export_profile.py --offline` 更新生成夹具；修改宿主代码后另运行 `python3 tools/prepare_browser.py --offline`。
8. 原生或浏览器以 `--developer --level <metadata.id>` 启动验收，使用独立 `--workspace-store`、`--settings-file` 和 `--save-file`。正式玩家仍按原存档解锁。无需修改 CLI choices、注册列表、UI 分支或 Level Manager。

加载器自动扫描 `.yaml` / `.yml`，浏览器启动器也调用相同扫描器并发布生成目录。文件错误显示完整 File/Path/Reason。不要手工编辑生成的 JSON 或用新编号文件替换旧关卡。本次临时“第六关”只在自动测试的临时目录创建，不进入本目录。

## 单位与受支持范围

位置为 m、角度为 rad、速度/角速度为 m/s 和 rad/s，炮台程序输入为 rad/s²；协议消息和端口名字保持现状。clock 中物理、子步、基础传感器和算法频率分离；基础传感器采样率须与现有 Core 一致，Radar 必须整除物理/基础传感器率。规则用仿真 tick，渲染继续独立插值。

公共标定用受限 `source` 引用模型尺寸/武器参数，不能引用敌方当前位姿或巡逻路径。教材中的数量/频率/噪声可使用公开占位符，避免修改参数后出现陈旧说明。所有修改都应验证原玩家源码兼容与不覆盖 Workspace。
