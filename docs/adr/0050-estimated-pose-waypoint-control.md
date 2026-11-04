# ADR-0050 基于玩家估计的航点闭环与轮驱动参考

- Status: Accepted
- Date: 2026-11-04
- Scope: Navigation C3及可复用航点组件；不改变既有物理或旧关卡接口

## Context

Navigation C2已实现轮控制与GPS/EKF，但目标Twist仍由系统按时间发送。用户要求继续开发位置闭环，已确认复用现有底盘/传感器和三个玩家算法，新增WaypointController，采用公开方形航点和120仿真秒。到点0.35m、终点连续停稳0.5秒、速度限幅和安全/评分细节均已确认。

当前cmd_vel在速度伺服场景属于实际执行器，在轮电压场景属于驱动控制器的参考；直接沿用现有执行器授权会混淆两个角色。现有模块图冻结输入并固定提交，不能通过同批函数调用隐去管线延迟。

## Decision

采用声明式waypoint_route任务组件和当前目标Topic，玩家位置控制器读取自己的EKF候选与目标，发布Twist参考，轮控制器继续发布电压。参考通过明确references白名单授权；Authority在wheel_voltage模式只把该Twist交给参考缓存/曲线，不送入速度伺服。禁止参考与执行器重叠或多个发布者争用同一Topic。

保留固定tick和跨批次通信，模块预算写入新关YAML。当前关目标、任务图层和参数均由配置决定；数值全部写入新关YAML，不修改旧关参数。旧九关、源码、revision/ledger、存档身份与CLI只读查看入口继续兼容。

## Alternatives

以目标速度直接覆盖真实速度会绕过电机和权限；强制新增传感器会扩大课程跨度；在Runtime内同批直连会改变既有模块时间合同；仅因Topic叫cmd_vel而把速度参考当作物理执行器会模糊驱动边界。本次采用显式参考角色及已有电压接口。

## Consequences

需要同步参考授权、任务/消息Schema、SDK适配器、任务状态和授权UI。状态机必须区分准备、正式控制、计时、按序到点、停稳和终局，不让测试或重部署重新开始任务。真值只供私有任务评价；允许公开哪些离散反馈须在关卡规范中明确。

## Acceptance Evidence

用户已确认全部任务与安全边界。287项Python回归、14个Node测试文件共67项测试通过，覆盖原九关配置冻结、参考无物理旁路、时间/缺测/数值负例、源码进度保护。Linux/Firefox中，原生与WASM/Pyodide均完成真实编辑、升级、测试、部署、四航点停稳通关和重试；故接受本决策。设计见 [37](../37_NAVIGATION_WAYPOINT_CONTROL.md)，实际结果与截图见 [验收报告](../reports/NAVIGATION_WAYPOINT_CONTROL_VALIDATION.md)。

此状态不表示其他OS/浏览器、硬实时或任意替换地图已经验证；已有本地Python隔离边界与20ms墙钟预算的限制继续有效。
