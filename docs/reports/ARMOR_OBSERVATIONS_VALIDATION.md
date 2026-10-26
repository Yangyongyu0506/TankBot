# C5 匿名装甲观测验收

历史范围：本报告记录当时的 C4 GPS/人工武器课程；当前 C4 已改为 C3 同款观测下的程序自瞄，C5 模型不变。当前证据见 [中心自瞄验收](CENTER_AUTO_AIM_VALIDATION.md)。

日期：2026-10-26。环境：Linux x86_64、CPython 3.14.4、Firefox 157.0.1、Node 22.22.1、Rust 1.99.1、Pyodide 0.29.5。需求确认与接口见 [30](../30_ARMOR_OBSERVATIONS.md)、[ADR-0037](../adr/0037-anonymous-armor-observations.md)。

## 实际改动与兼容

C5 用同一 YAML 加载器组合 armor_detector、匿名观测 SDK、跟踪与预测/控制组件。C0–C4 的五个 YAML 未修改。敌车动力学、装甲几何/伤害、控制权、双方 HP、时限和通关条件未改变；仅替换 C5 观测、对应教材/合同和对称朝向评价。

C5 不再生成或授权中心 Radar/GPS；新 payload 只有当前 0/1/2 行 [r,theta]，没有实体 ID、装甲 ID、中心 fix 或真实 yaw。新脚手架 4.0.0 通过预览升级管理文件，原融合器、预测器、控制器和历史保留。三份玩家文件均在真实 F2 tree 中高亮。

## 自动化结果

- Python 全量 **182 项通过，106.655 s**；日志为 `.m1-cache/c5-armor-observations/python-tests.log`。
- 新增 6 项装甲领域测试覆盖自身坐标变换、正面可见性、逐块墙遮挡/量程边界/死亡、0/1/2 条、独立可复现噪声/丢失、负距离与角度归一、四重旋转及装甲重编号不改变匿名观测、SDK 不可变/有界、Schema 负例、权限、相位评分及源码保留。
- 原生数值闭环中，新参考算法只读授权装甲与自身/武器状态，C5 在 1027 tick 存活击杀；位置 RMSE 0.0281 m，模 90° 相位 RMSE 0.1235 rad。参考源码仅在测试目录，不作为玩家默认答案。
- Rust **18 项通过**，既有运动、接触、武器、紧凑装甲与生命判定保持。
- Node 相关 **22 项通过**：渲染 15、设置/图层 5、装甲局部显示 2；新局部显示不制造坐标或身份，也兼容原中心 Radar。
- 既有原生/WASM 同工具链一致性检查通过：两底盘各 600 tick、巡逻 1800 tick、炮台/装甲 600 tick、小陀螺 600 tick。
- 生成夹具和浏览器可信/玩家源码包均更新；协议与 SDK 不引入新第三方依赖。

## 真实网页 Test / Deploy

使用独立 settings、progress、Workspace 与专用无头 Firefox，在玩家模式依次运行 C3→C4→C5。通过 CodeMirror 实际编辑高亮文件、保存、预览管理脚手架升级、Test 得到 Ready、Deploy 得到 Active，然后完成手动/自动击杀；不是直接向页面注入真值控制器。

| 运行方式 | C3/C4 | C5 | 终局位置 RMSE |
| --- | --- | --- | --- |
| 原生 Authority | 正常测试、部署、人工击杀 | 新三文件、匿名传感器、程序自主击杀 | 0.020 m |
| 浏览器 WASM/Pyodide | 同上 | 同上 | 0.027 m |

C5 的授权画面观测包含 joint_states、imu、turret/joint_states、weapon state 和 armor_detections；明确检查没有 /robot/sensors/radar 或 /robot/sensors/intercepted_gps。传感器页实际显示匿名装甲的数量、r/θ 数值和局部点；位置/相位图形来自玩家估计。部署后编辑器自动退出且运行期锁定，页面无整体滚动。

工具：`tools/browser_m5.py`。JSON、截图及日志位于 `.m1-cache/c5-armor-observations/`，使用临时源码库，不修改用户日常项目。后续复验需分别连接原生服务与带 `?runtime=browser` 的浏览器服务。

## 限制与开放项

匿名方形装甲只能辨识模 90° 的布局，本轮不提供真实车头答案或稳定编号。单块可见/连续丢失时需要历史预测，参考 EKF 可达性不代表唯一解法或学习效果。多目标、杂波、真实图像/PnP、异步传感器、非对称装甲和其他 OS/浏览器尚未验证。
