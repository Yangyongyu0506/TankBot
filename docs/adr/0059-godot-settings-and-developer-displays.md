# ADR-0059 Godot设置与独立开发者显示

- Status: Accepted
- Date: 2026-11-18
- Scope: 用户确认的设置、键位、图层与数据查看器恢复；验收限Linux Godot原生流程

## Context

Web退役后，设置YAML、进度校验和独立DeveloperSnapshot仍在后端，Godot只有读取键位和少数显示开关。用户明确要求完整恢复F10/设置弹窗、键位与默认值、玩家/开发者切换、独立图层和数据查看器。需要延续ADR-0026、0055、0057及0058，不能通过恢复GUI把真值加入普通视图、Python输入或定位状态。

## Decision

复用GET/POST `/api/settings` 的revision/CAS及原文件锁/原子写入，保持version=1、稳定关卡ID、源码目录和历史。设置使用固定视口内嵌面板，标题/保存/取消固定，键位与图层内部滚动；捕获物理键、不支持组合或重复绑定，Esc先取消捕获。Godot从JSON读取的版本数值在提交时显式编码为整数，不放宽后端校验。

玩家显示取关卡allowed_layers、user_toggleable、initial_enabled和preserve_user_settings；开发者在此之外取得独立管理grant。私有快照只经 `/api/developer` 进入独立缓存/插值及Sprite/诊断层，绝不改写公开时间线、Pose Selector、物理或玩家输入。敌车使用自己的target_visuals；没有估计位姿时，真实车体属于明确开发者图层，不作为玩家估计回退。

图层、轨迹和查看器有界；扫描地图投影只用同run/revision/source/frame且同sample tick的玩家EKF，开发者真值也不能替代该匹配。开发者和玩家时间线可使用同一仿真显示时刻，不向未来外推。关闭grant先清空私有节点、缓存和查看器，异步响应按grant世代与run拒绝；其他窗口改模式后由轮询撤权重载。

同日用户补充确认：开发者动态实体统一50%不透明度，墙体/障碍不变；坐标轴与点线置于场景最上层。车辆先经CanvasGroup合成，再统一调透明度，system位姿与真值车体不重复叠画。地图填充、实体和诊断标记采用YAML声明的独立绘制顺序；不授予新信息、不改变既有显示开关。

模式切换要求先结束尝试并等待Start检查结束；普通改键/图层不重建尝试，打开设置不会暂停正式计时。结束尝试的UI状态使用独立世代，防止同run旧轮询恢复“运行中”。已保存VS Code文件、revision/ledger和玩家正式进度保持；开发者预览不奖通关。

## Alternatives

只恢复模式复选框不足以满足用户确认范围；复活Web会违反0057；直接把私有数据并入PlayerViewSnapshot会破坏0026。每帧读取磁盘或重新创建全部Sprite增加无用成本，采用原管理API、共享纹理和有界状态。设置页使用固定Control面板，避免嵌入Window自动最小尺寸把保存按钮挤出视口；数据查看器继续复用只读对话框。

## Consequences

增加Godot显示组件和客户端专用desktop-tools YAML/Schema，不增加运行依赖或机器人协议。原生20ms声明额度、30ms实验性墙钟、固定6tick及物理/评分不变。键鼠和图层管理已恢复，不等于恢复手柄、曲线、实验台、任意RViz插件或独立发行包。普通CPython仍不是OS强沙箱，本机开发者模式不是远程竞技授权。

验证见 [Godot设置与开发者验收](../reports/GODOT_SETTINGS_AND_DEVELOPER_VALIDATION.md)：真实改键/CAS、C5/C6、撤权及源码/进度保留。跨平台、其他分辨率和长期运行可靠性未由该验收覆盖。
