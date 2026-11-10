# 接口样例与验证夹具

## 当前范围与使用方式

本目录提供结构正例、反例描述及历史接口示意，不是可直接部署的玩家工程。可运行的启动示例在根examples/robot；正式关卡由levels/*.yaml生成与授权。Protocol 1.0和SDK 0.1.0是当前仓库未发布profile，`run-demo-001`、publisher与profile名称只是示例身份，不授予权限。

当前应用配置为2.1、课程十一关；样例中的M3/M4/M5名称保留当时接口形状。消息兼容不意味着示意Manifest可用于任意关卡，测试/部署仍要求当前Contract图、库策略、环境摘要和冻结执行profile。

## 目录索引

| 文件 / 分组 | 用途与边界 |
| --- | --- |
| [pose-message](pose-message.json)、[imu](imu-message.json)、[encoder](encoder-message.json)、[joint-state](joint-state-message.json)、[radar](radar-message.json) | 类型化测量/候选，保留采样tick、单位和frame |
| [cmd-vel](cmd-vel-message.json)、[全向Twist](cmd-vel-omni-message.json)、[chassis-controller](chassis-controller.json) | 连续车体速度与watchdog；无执行起止字段，非零vy只适用于全向能力 |
| [全向轮标定](omni-wheel-calibration.json) | radial_omni@1公开几何；不代表轮电机或打滑模型 |
| [炮台速度](turret-velocity-message.json)、[角加速度](turret-acceleration-message.json)、[单发](fire-command.json)、[武器状态](weapon-state-message.json) | 独立执行器消息；是否授权由课程决定 |
| [目标点](target-estimate-message.json)、[目标位姿](target-pose-message.json)、[匿名装甲](armor-detections-message.json) | 玩家估计或匿名局部测量，不包含隐藏敌车真实状态 |
| [GPS位置](position-fix2d-message.json)、[航点目标](waypoint-goal-message.json) | 我方带协方差GPS与公开任务目标；没有当前真值输入旁路 |
| [估计视图](view-snapshot.json)、[真值练习视图](weapons-practice-view.json)、[目标估计视图](campaign-view.json)、[位姿对照](pose-comparison-view.json) | 不同view_snapshot版本和显式授权，不能混为原始World |
| [view-policy](view-policy.json) | 禁用系统源的受信策略结构，不是玩家提权申请 |
| [runtime请求](runtime-step-request.json)、[响应](runtime-step-result.json)、[遥测](runtime-telemetry.json) | 固定激活/提交的私有控制面；遥测不可信、不是CPU额度 |
| [运行profile目录](runtime-execution-profiles.json) | 当前新目录结构与实验性后端默认；兼容/优先级合同见41 |
| [协商请求](negotiate-request.json)、[响应](negotiate-response.json)、[错误](error-event.json) | 结构夹具，不证明正式远程协商或服务器已发布 |
| [周期Contract](module-contract.json)、[event Contract](module-contract-event.json) | 两种已实现调度模式的结构样例；端口与额度仍须经实际任务准入 |
| [M3 Manifest](m3-workspace.json)、[Contract](m3-module-contract.json) | 历史单模块本机形状，仍用于兼容测试 |
| [M4 Manifest](m4-workspace.json)、[Contract](m4-module-contract.json) | C0–C2兼容包装的历史形状，不代表全部十一关只用一模块 |
| [M5 Manifest](m5-workspace.json)、[Contract](m5-module-contract.json)、[路径Contract](path-follower-contract.json) | 图结构和追踪器端口；当前每关模块/参数由YAML生成 |
| [早期通用Manifest](tankbot.json) | main:build_robot目标设计示意；动态RobotApp/工厂尚未实现，不能当受管可运行工程 |
| [分支进度](branch-progress.json) | 版本1非连续完成集合；不要求Weapons通关后再学Navigation |
| [工程配额](engineering-settings.json)、[完整备份](workspace-backup.json) | 公共结构样例；磁盘引用/CAS/安全路径另验 |
| [空录制](experiment-empty-record.json)、[空实验包](experiment-empty-package.json) | 仅结构夹具；真实比较需要非空授权输入和兼容上下文，没有私有目标参考 |
| [validation-cases](validation-cases.json) | 单点/多点修改的结构与领域负例，覆盖层级见下文 |

## 验证层级与时序

样例中的publisher_id和频道字符串不提供权限，Authority绑定实际身份/租约。若cmd_vel样例生成于tick120、提交于126，且配置watchdog为0.5s，则tick150失效；时刻由Host/Controller计算，不由玩家写入payload。

validation-cases.json的mutation/mutations按JSON Pointer修改正例；context是测试装置输入，不是线上消息。schema负例必须结构拒绝；domain负例必须结构通过，再由行为验证拒绝。文档工具只检查分层，test_protocol_fixtures.py直接接入其中10个协议领域案例；图、权限、工作区等另有回归，不能将未逐项绑定的案例说成全部完成或将相关功能整体说成未实现。

```bash
python3 docs/tools/check_design.py
python3 tools/export_profile.py --check --offline
```

前者离线检查正/反结构夹具、片段和引用，后者核对同一YAML加载器生成的Core测试配置，不执行玩家完整通关。完整本地/CI入口见 [38](../38_ENGINEERING_AND_ALGORITHM_LAB.md)，结构说明见 [Schema索引](../schemas/README.md)。

## 历史与扩展约束

M3只验收单模块，M5随后实现声明式模块图和event；早期build_robot设想不因此自动变为SDK API。当前路径生成、任务裁判和readonly数组见 [40](../40_NAVIGATION_CONTINUOUS_PATH_TRACKING.md)，profile拆分见 [41](../41_RUNTIME_EXECUTION_PROFILES.md)。当前源码、历史报告及待验证项分开记录，不修改旧样例数值来伪造新验收。

修改公共接口时同步正文、Schema、SDK、样例和行为测试；新增Schema不代表已实现服务、scan/SLAM、任意多机器人或Arena。玩家估计、授权测量和裁判真值始终分离。
