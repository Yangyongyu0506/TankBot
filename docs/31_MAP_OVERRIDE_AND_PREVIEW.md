# 31 启动地图覆盖与授权预览

## 范围与接口

在既有地图资产加载器上增加启动覆盖与只读预览，不添加新关卡或地图热切换。决策见 [ADR-0042](adr/0042-map-override-and-preview.md)，地图与布局见 [资产目录](../assets/maps/README.md)。

```bash
python3 tools/tankbot.py --list-maps
python3 tools/tankbot.py serve --level c0 --map open_large
python3 tools/tankbot.py browser --level c0 --map maps/navigation_warehouse.yaml
python3 tools/tankbot.py headless --level c0 --map open_large --ticks 600
```

`--map` 接受资产名称（可省略 .yaml）、`maps/…yaml` 或 `assets/maps/…yaml`；文件必须在 assets/maps 内。禁止绝对路径、路径穿越和目录外符号链接。`--list-maps` 自动发现 YAML，验证后输出路径及墙体数量，不启动仿真或修改用户存档。

## 生命周期与配置优先级

启动器先选择关卡与底盘，再解析 CLI 地图。优先级为 **启动覆盖 > 关卡地图 > 自由试验场地图**。解析后的 `map_override: {path, walls}` 是本次进程的内部配置，Schema 验证其结构；不写回源 YAML、设置或存档。关卡重新配置后重新应用覆盖，因此重试、切关、模式切换及浏览器页面重载都不会悄悄恢复绑定地图。停止服务、重新启动且省略 --map 即恢复默认地图。

原生和浏览器分别调用同一 `maps.apply_override`；Core 最终仍收到 scene.walls，物理、遮挡、视图同源。私有 Core DTO 不需要 map_override 元信息；玩家 SDK 消息不变。

## 初态冲突与约束

地图覆盖不修改初始位姿、巡逻路线、敌车、传感器或任务。创建 Core 前，以旋转车体外包矩形检查玩家和目标与墙的重叠；失败返回 MAP_SPAWN_BLOCKED，含资产路径、墙索引和机器人名称，不自动瞬移或删除障碍。检查保守地包含圆角矩形四角；不声称为精确圆角接触查询。它不保证巡逻路线无碰撞或任务可解。

例如 navigation_slalom 原点在墙中，直接覆盖零初态关卡会拒绝；必须在自定义场景中明确指定安全初态后使用。后续可设计独立场景编辑/出生点功能，本次不隐式引入。

## 自定义练习与存档

用户明确选择：任何 --map 覆盖均为自定义练习，即使选中与原关相同的地图。保留原任务判定、正式时限和关卡解锁权限，但成功不写 completed_levels、不解锁后续关卡。已有源码、历史版本及既有完成记录保留。

ApplicationState 在注册尝试时将 practice 绑定到服务端 ticket；完成请求不能通过客户端字段改成正式成绩。原生和浏览器都传入此标记；开发者模式仍按原规则不计成绩。public_profile 的 custom_map_practice 为新增只读 UI 字段，画面常驻提示练习状态，终局文案不会误报已解锁下一关。

## 预览与权限

顶部「地图预览」打开模态弹窗，显示地图全景、原点与世界轴、网格刻度、外包尺寸和墙体数量。外包尺寸包括墙厚，与资产目录所写的内部净尺寸区别明确。开发者可选择任意发现的地图，预览不改变当前仿真，并提供 --map 启动示例。普通玩家只得到本关授权公开的当前地图；未授权时显示说明，不发送墙体或资产路径。

`GET /api/maps` 返回 current（或 null）、maps（开发者资产目录，普通玩家为空）、overridden、override_path（未授权时 null）、developer。服务器同时检查 scene.public_map、View Policy.public_map 和关卡 allowed_layers；不以 CSS 隐藏实现权限。播放器 Runtime origin 不提供此接口，也不开放资产目录静态下载。浏览器本地模式的既有客户端信任限制保持。

预览按完整包围盒等比例绘制，不跟随坦克、不旋转世界轴；主游戏仍沿用授权快照和跟随相机。弹窗中驾驶/开火/手柄编辑入口被抑制，F1/F2/F10 不叠加其他弹窗；Esc 或 × 关闭后聚焦游戏。预览不暂停正式尝试，不新增网页滚动。

## 验证与限制

自动测试覆盖 CLI/路径、所有关卡重配后的覆盖保留、初态冲突、隐藏地图拒绝、两种 HTTP 服务、练习 ticket 和正常成绩，以及预览坐标/空图绘制。真实 Firefox 验证使用独立 settings/save/workspace，工具为 `tools/browser_maps.py`；不对玩家 userdata 做改写。

本次没有地图热切换、缩放漫游编辑、导航路径生成或任意初态自动修复；这些需要独立设计。地图命名来自资产文件名，未来本地化地图元信息尚未实现。

### 本次验收（2026-10-29）

- 完整 Python 回归：197 项通过；最终路径与中文错误响应修订后，地图覆盖专项 5 项再次通过。
- Node：地图预览 2 项、渲染 15 项、编辑器尝试锁 4 项、设置/权限 5 项通过。
- 原生及浏览器 WASM 的真实 Firefox 均通过：地图资产列表、全景渲染、只读预览、按键隔离、关闭后焦点、重试保持覆盖及异步刷新保留选择。
- 实测视口为 1280×814 与 500×654，无页面滚动和弹窗越界；未将 Firefox 最小窗口宽度约束下的 500 px 实测描述为 390 px 设备验证。
- 原始报告与截图在本机 `.m1-cache/map-preview/native-ui.json`、`browser-ui.json` 及同目录 PNG；工具为 `tools/browser_maps.py`。全部使用隔离的临时存档和工作区。
- 文档、Schema 夹具、生成 profile 检查及 git diff --check 通过。浏览器资源包已更新；本轮没有重新验证 Windows/macOS 或真实移动设备。

## 自动路径课程的覆盖约束

Navigation C4覆盖地图仍为练习，但必须满足其完整车体、路线长度、端距及明显绕障的既定生成约束。空旷地图无法提供被障碍阻断的直达路线，会有界报PATH_GENERATION_FAILED；不暗中移除绕障要求或提供固定替代路径。仓储资产可按相同通用覆盖接口使用。重试复用已解析路径，切图须重新解析；详见 [40](40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)。
