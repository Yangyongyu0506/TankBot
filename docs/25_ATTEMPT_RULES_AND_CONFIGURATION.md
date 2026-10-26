# 25 关卡计时、玩家生命与参数配置

## 目的与范围

为每关提供有限运行时间、明确失败原因和主动结束入口。编辑时间不侵占首次正式运行的预算；从 C2 开始，玩家与敌车使用相同生命规则。沿用固定 tick、真实弹丸碰撞、World 权威和既有非覆盖 Workspace，不增加敌车主动开火功能。

## YAML 为唯一可编辑配置源

`config/game.yaml` 定义通用物理、控制、渲染、Runtime、预算及插件目录。独立 `levels/*.yaml` 定义每关的世界/机器人组合、传感器、权限、目标、时限、终局顺序和教学说明，见 [27](27_LEVEL_PLUGIN_ARCHITECTURE.md)。`campaign.levels`、`campaign.lessons` 等旧形状由加载器生成，供既有内部接口使用，不能作为第二套手工配置。课程库策略在 `config/player-dependencies.yaml`，个人键位与模式仍在 `userdata/settings.yaml`。

后续新增可调整数值、模型系数、容量、频率和关卡数据必须放入相应 YAML，并在 Schema 中声明；不得在 Python/Rust/JavaScript 中复制默认参数或失败时静默填入数值。数学定义、单位换算、类型/协议标识符属于接口语义，不能为了外置参数而改变其含义。新关卡复用已注册组件时只需添加 YAML 并完成教学验收；未知组件/规则须先扩展引擎和验证，不能仅添加配置就声称已支持。

宿主使用 SafeLoader，拒绝重复键、对象标签、循环别名、非有限数值和不能表示为 JSON 的值，再执行 Schema/领域校验。YAML 不直接发送给玩家 Runtime。宿主把解析后的受信配置通过既有私有 JSON DTO 交给 Rust/WASM；JSON 协议、存档、Schema 和依赖锁文件保持其格式。

Rust/Node 测试及 WASM probe 使用生成的 `core/tests/fixtures/default-profile.json`，禁止手工维护第二份数值。`python3 tools/build.py` 自动运行 `tools/export_profile.py`；直接 Cargo/Node 开发前可执行 `python3 tools/export_profile.py --offline`。`python3 tools/export_profile.py --check --offline`、文档检查和配置单测都会拒绝过期夹具。默认 CLI 改为 YAML；自定义 JSON 仍可作为私有 Adapter/兼容输入，但新版本 Campaign 必须提供所有新字段，缺失时明确拒绝，不猜测时限。

应用配置基线 `2.0`，关卡 Schema 为 `1.0`。独立底盘几何/安装/外观在 `config/chassis/*.yaml`，由 `game.yaml` 显式引用，见 [29](29_CHASSIS_PROFILES.md)。旧报告记录的 JSON 路径和源码摘要描述当时构建，不能当作当前 YAML 的验证摘要。

## 时间与开始边界

| 关卡 | 默认时限 | 起算 |
| --- | --- | --- |
| C0 | 60 仿真秒 | 首次被 Authority 接受的非零驾驶/炮台输入或有效开火意图 |
| C1 | 60 仿真秒 | 首次已测试玩家快照成功激活的固定 tick |
| C2 | 120 仿真秒 | 同 C1 |
| C3 | 120 仿真秒 | 同 C1 |
| C4 | 120 仿真秒 | 同 C1；模型/判定沿用 C3，程序自动武器 |
| C5 | 180 仿真秒 | 同 C1 |

准备阶段的自动中立输入、编辑、单元测试、候选仿真测试、失败部署均不启动倒计时。C1–C5 未正式部署前关闭人工开火；驾驶在 Weapons 章节始终禁用，防止准备期完成目标；物理仍可为测试提供授权传感器。显式无头/CLI 工作区直接执行的代码视为启动部署，在成功初始化后从首个仿真 tick 起计时；浏览器加载的系统脚手架不算玩家部署。

成功激活记下 `started_tick`，总预算为 `time_limit_s * physics_hz`。仿真与渲染、系统墙钟独立。正式开始后持续计时，算法崩溃不暂停。UI 在 running 阶段锁定编辑器，须先结束或重置关卡再编辑；底层管理接口的重新测试、失败部署、再次部署和回滚仍不暂停/重置倒计时。只有重新开始关卡才建立新预算与 World。浏览器后台节流可能降低仿真推进速度，因此这不是竞技服务器的真实时间计时器。

## HP、死亡与结算

C0/C1 `player_health: null`，沿用受击计数而不扣血。C2–C5 配置 `same_as_target`，由宿主从本关敌车 `health` 派生同一份玩家模型：当前 3 HP、每次弹丸命中扣 1 HP、接触墙体不扣血。不存在写在实现内的第二组 HP 常量。弹丸归属不免伤，离膛保护结束后的反弹自伤也计入。

弹丸命中仍按世界速度动量、底盘能力投影、偏心角冲施加冲量，不增加坦克质量。Core 在固定子步末扣到零时移除玩家底盘、炮台、关节与碰撞体，不留残骸；后续子步不再伺服、采样或碰撞已移除的玩家。既有弹丸继续运行，不能命中幽灵碰撞体。Authority 在该 tick 末关闭 Runtime/候选、撤销控制并判定失败；授权视图清除车体与旧观测，开发者层也不绘制已销毁车体。

默认优先级：玩家死亡 → 时限内完成目标 → 超时。双方在同一物理 tick 死亡判失败；玩家存活且在最后一个预算 tick 完成目标可以通过；超过边界不能补记通关。终局报告不可变，结束后的剩余弹丸不会改写本次成绩或奖励存档。

## 管理接口与 UI

沿用 `GET /api/campaign` 和 `POST /api/campaign/finish`（浏览器为同名 Worker RPC），不新增玩家消息权限。

`attempt` 保留原有 `status: active/passed/ended`，增加 `phase: preparing/running/finished`；`timing` 包含 `time_limit_s/start_on/started_tick/elapsed_ticks/remaining_s`。已授权关卡显示 `player_hp/player_max_hp`；敌方 HP 仍按 capability 裁剪。`result.reason` 为 `objective_completed/timeout/player_dead/aborted`。客户端不能提交时间、HP 或 passed。

画面固定显示倒计时与双方 HP，编辑器也显示同一权威状态。任务页和编辑器都有「结束本次尝试」，不用等待超时。主动结束关闭执行与待提交输出，保存的源码及未保存编辑草稿不因结束被覆盖；结束后可继续修改和保存，先重试关卡再测试/部署。失败不会解锁下一关。

## 取舍、验收与开放项

选择仿真 tick 计时以保持原生/WASM 一致；墙钟倒计时会使慢设备得到较少控制步。继续使用明确终局和重试，不自动暂停编辑器，避免运行预算语义随 UI 焦点变化。HP 由真实碰撞生成，不接受客户端受击或扣血请求。

验收覆盖 YAML/夹具一致、参数错误、准备/测试不计时、部署起算、重复部署不重置、主动结束、准确截止 tick、同时死亡与最后 tick、实际反弹自伤扣血及移除、两种 Runtime UI。证据见 [验收报告](reports/ATTEMPT_RULES_VALIDATION.md)。默认时限的教学难度、其他 OS/浏览器及长期运行仍需后续验证；本次不宣称完成敌方攻击 AI 或 Arena 时钟。
