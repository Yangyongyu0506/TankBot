# 36 公共入门与双主线关卡树

## 目的、范围与要求

让玩家任选目标感知/自瞄或底盘/自身定位主线，保留各自主线真实的知识和代码依赖。原进度重构只修改当时九关的选择界面与解锁；后续用户授权增加Navigation C3/C4，当前共十一关，见 [37](37_NAVIGATION_WAYPOINT_CONTROL.md)、[40](40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)。用户已确认依赖，实施状态见 [ADR-0049](adr/0049-branching-course-progression.md)。

```mermaid
flowchart TD
    I[c0 公共入门] --> W1[Weapons C1 坐标变换]
    I --> N0[Navigation C0 轮驱动]
    W1 --> W2[C2 目标跟踪]
    W2 --> W3[C3 极坐标滤波]
    W3 --> W4[C4 预测与自瞄]
    W4 --> W5[C5 装甲与小陀螺]
    N0 --> N1[Navigation C1 里程计]
    N1 --> N2[Navigation C2 GPS/EKF]
    N2 --> N3[Navigation C3 航点位置闭环]
    N3 --> N4[Navigation C4 连续路径追踪]
```

实线均为必须通关的前置。公共入口保留Hello Robot章节与c0存储身份；Weapons和Navigation原章节ID、文件名及metadata.order不变。跨主线建议只进入现有关卡tutorial.hints，不影响解锁，也不复制算法。

## 单一规则与存档

metadata.prerequisites数组表示全部前置完成。ApplicationState统一判断CLI、选关API、浏览器启动ticket和正式完成存档；开发者保留自由练习，地图覆盖练习不奖进度。完成不等于部署、测试Ready或主动结束。锁定提示列出缺少前置的名称和稳定ID。

沿用version=1、completed_levels、current_level与completions。完成集合无需是全局前缀，[c0,navigation.c0,navigation.c1]合法；完成项仍按原目录顺序写出，读取不排序重写，旧顺序与当前关卡保留。目录只校验已知前置和无环，不从order产生权限。正式Schema仅约束ID格式，已知ID、前置闭包、稳定序列化顺序及记录一致性由领域层验证。

## 目录与界面合同

公共catalogue/profile在既有level_id/title/problem/chapter_id之外返回prerequisites、order、description，来自同一YAML。UI以服务器unlocked_levels为状态依据；目录前置用于连线和具体缺失说明，不是额外授权规则。

公共入口置顶，其余按章节分列；节点与所有实线从目录生成，不写死九关关系。节点展示已通关、可挑战、锁定及独立的当前标记。锁定节点可以查看任务/前置，但开始按钮不可用；服务端仍验证请求。通关列出本次新开放的所有节点，允许任选或重玩，不强制自动进入下一关。

选择器使用固定视口弹窗、独立图内/详情滚动，窄屏可纵向分组。按钮可Tab/Enter/Space操作，Esc/×关闭；打开释放控制，禁止手柄或F2穿透到游戏/编辑器。现有任务面板保留当前关卡开始/重试与主动结束。

## Workspace与生命周期

默认campaign和navigation分组不变。只完成c0即可创建独立Navigation工程；返回Weapons复用原库。原生在成功创建候选Authority/Workspace后原子切换并关闭旧运行；浏览器切换对应配置/库后刷新，关闭旧Worker及缓存。保存、测试、部署和模板预览均沿用已有机制，不修改玩家源码或历史。失败切换保留当前运行与工程。

## 启动前查看依赖树

```bash
python3 tools/tankbot.py --level-tree
python3 tools/tankbot.py --level-tree --save-file /path/to/progress.json
```

无需serve/browser运行模式。命令加载同一关卡目录，按YAML前置生成文本树，标出已通关/可挑战/未解锁、当前关卡及缺少的前置。默认读取userdata/progress.json；缺失时只在内存生成新玩家预览，不创建用户数据目录、设置、存档、锁文件或Workspace，也不启动Core、Python玩家程序或Web服务。开发者开关不影响展示的正式通关记录，查看不会更改模式。

ApplicationState继承host/tankbot_host/progression.py的LevelProgression，复用同一组前置、解锁和版本1存档校验。命令直接使用该目录规则组件读取一次原子保存的文件，不构造有初始化写入的ApplicationState；损坏/不兼容存档报错并保留。既有服务读改写仍使用原OS锁/原子替换机制。多前置节点明确列出全部要求，并在各父节点下显示引用，后代只展开一次；数量、ID和章节不硬编码。--config可选择另一目录配置，--list-maps与--level-tree互斥。首次运行仍沿用现有Python依赖引导机制，可使用--offline复用已准备的缓存。

回归见tests/test_level_tree_cli.py，覆盖无副作用、非连续/旧存档、两分支开放、多前置共享节点、展示顺序独立及损坏文件拒绝。游戏内交互查看继续使用顶部或任务面板的「关卡路线」。

## 取舍、开放项与验收

只开放同主线真实依赖，避免“解锁但缺前序算法”；全自由选关仍留给开发者。树只解决路线阻塞，不证明单关难度已经平滑。未来新增插件仍需完整教材与可玩性验收，多机器人/更多推荐系统不属于本轮。

验收覆盖新档双分支、Navigation独立通关记录、互不越权、旧档/非前缀集合、API/CLI、未知/环/展示顺序独立、地图练习与开发者、源码/历史往返，以及原生和浏览器真实玩家界面，结果见 [双主线验收报告](reports/BRANCHING_PROGRESSION_VALIDATION.md)。历史报告描述当时的链式规则，不改写。
