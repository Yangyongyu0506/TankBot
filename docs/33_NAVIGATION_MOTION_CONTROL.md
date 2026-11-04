# 33 Navigation 首关：双轮运动控制

## 目的与范围

Navigation 首关稳定 ID 为 navigation.c0，通关公共c0后即开放，与Weapons C1并行，开发者仍可直达。当前进度见 [36](36_BRANCHING_PROGRESSION.md)，不再要求完成Weapons C5。只保留差速底盘，不创建炮台、武器、敌车或血量，不加载Weapons工程。玩家不能人工驾驶；系统发送Twist，玩家实现FK/IK与电机控制，输出两轮电压。[原验收](reports/NAVIGATION_CONTROL_VALIDATION.md)保留当时链式入口的历史，物理/接口/阈值未改。

物理参数集中在 [差速底盘](../config/chassis/differential.yaml)，指令、权限、教材与评价在 [关卡 YAML](../levels/navigation.C0.yaml)。`robots[].drive: wheel_voltage` 选择新驱动；省略时继续 velocity_servo，保持旧关卡轨迹。`world.weapons_enabled: false`、`objectives.target: null` 表达无武器/目标场景；加载器拒绝矛盾的武器控制、生命与敌方/武器传感器。不存在隐藏靶标或关卡 ID 物理分支。

## 组件与数据流

```mermaid
flowchart LR
    Y[YAML twist_sequence / 仿真时钟] --> T[/robot/cmd_vel]
    T --> C[玩家 WheelController.control]
    E[/robot/sensors/joint_states] --> C
    C --> A[/robot/wheels/cmd_voltage]
    A --> M[轮电机 / 轮地反力 / 刚体]
    M --> E
    M --> P[Core 真实位移与路程]
    P --> V[View Policy / 系统自身位姿]
    P --> R[声明式评价]
```

## 已确认模型、数值与约束

轮端等效参数：R=2 Ω、Kt=0.5 N·m/A、Ke=0.5 V·s/rad、每轮 Jw=0.01 kg·m²，U 限制 ±12 V；不加电感、电流限幅、死区或噪声。保留车体 m=20 kg、I=2 kg·m²、r=0.1 m、B=0.5 m，以及 cx=4 N·s/m、cy=200 N·s/m、cw=0.8 N·m·s。数值从 YAML 读取，本文仅同步记录。

每个物理子步计算 i=(U−Keω)/R、τ=Kt·i。滚动关系为 ωL=(vx−Bwz/2)/r、ωR=(vx+Bwz/2)/r。无纵向打滑；侧向保留既有黏性运动，不引入轮胎模型。轮惯量反作用通过 m_eff=m+2Jw/r²、I_eff=I+JwB²/(2r²) 计入驱动。

旋转车体系内：m_eff·dvx/dt=(τL+τR)/r−cx·vx+m·wz·vy；I_eff·dwz/dt=B(τR−τL)/(2r)−cw·wz。Core 施加与这些加速度一致的实际力/力矩，Fy=−cy·vy；不设置目标真实速度，不内置轮速 PID。

碰撞使用既有圆角矩形、车体质量/惯量和非弹性接触；冲击后轮速按实际车体运动反算。**轮惯量仅在驱动方程内计入，不另建转子刚体，不声称完整轮系碰撞能量模型。** 零电压是短接电枢的电气制动，0.5 s 失联也置零；电压逐轮截断，NaN/Inf 先拒绝。

## 玩家接口与调度

框架创建 `WheelController(model)`；只编辑 `control/wheel_controller.py`，可增加辅助函数。完整类型、标定和返回值在 F2 及模板中可查。

```python
def control(
    self,
    target: Twist,
    wheel_rates_radps: NDArray[np.float64],
    dt: float,
) -> NDArray[np.float64]:
    """数组 shape=(2,)，顺序 [left,right]；输出单位 V。"""
    raise NotImplementedError
```

target.linear.x 是 m/s，target.angular.z 是 rad/s，其他轴为零。轮速是只读 float64 向量，单位 rad/s，仅含本帧；返回有限 float64 NumPy `(2,)`，错误形状/类型产生清晰异常。self.model 为只读 DifferentialDriveParameters；self.integral_error 是固定两项状态，不自动累计历史。每次部署/重试重新初始化控制器。

物理 60 Hz/4 子步，编码器 30 Hz，玩家 10 Hz，固定延后 6 tick 提交。沿用 Module/图调度、配额与 Runtime 隔离，玩家计算不能阻塞物理。测试输出不驱动车体，也不触发正式时钟。

新增 `wheel_voltage@1`：topic `/robot/wheels/cmd_voltage`、frame base_link，payload 为 left_voltage_v/right_voltage_v。旧 Envelope/消息保持；无执行起止时间。本关 `/robot/cmd_vel` 是 Authority→控制器的参考输入，不能由玩家绕过轮驱动直接发布。

```json
{
  "protocol_version": "1.0",
  "message_type": "topic",
  "channel": "/robot/wheels/cmd_voltage",
  "sequence_number": 0,
  "simulation_tick": 0,
  "simulation_time_ns": 0,
  "run_id": "run-demo-001",
  "publisher_id": "module:wheel_control",
  "request_id": null,
  "frame_id": "base_link",
  "schema": "wheel_voltage@1",
  "payload": {"left_voltage_v": 3.0, "right_voltage_v": 3.0}
}
```

## 固定指令与评价生命周期

YAML twist_sequence 四次交替：vx=0.5 m/s 直行 240 tick；vx=0、wz=π/4 rad/s 原地左转 120 tick。共 1440 tick/24 s。首次正式部署武装指令源，第一批合法轮控制在权威边界生效时开始计时；重复部署不重置序列或路程基线。指令承受既有提交延迟，不自动提前切换来掩盖控制滞后。

每个子步累加真实质心位移；最后转向段结束当刻检查 origin_distance_m≤0.30 m、path_length_m≥7.2 m，两项同时满足成功，否则 trajectory_failed。没有额外制动等待或朝向门槛。先判控制程序故障，再判成功、轨迹失败、超时；终局冻结本关仿真，保留结果、日志和源码。主动结束/重试可继续使用。

本关 visualization.trail_points=900 限制显示轨迹容量，覆盖整个尝试。终局保留同一授权系统位姿来源与视图纪元，因此不会清空轨迹；重试建立新 run 后清空显示缓存。轨迹图层仍可独立关闭，不影响真实路程评价。

规则仍走 compare/all/any/not，新增事实 sequence_complete、controller_faulted、origin_distance_m、path_length_m；YAML 不含执行脚本。运行中展示目标 v/w 以及分别获 allowed_metrics 授权的距离/路程，评分不依赖显示状态。**仅终点和路程不能排除走圆或反方向闭合路线**；按用户确认保留这两项标准，不私加唯一算法/方形拟合门槛。

## 独立项目与兼容

`scaffolding.workspace_scope: navigation` 仅决定项目管理。省略继续原 campaign 身份，所以 C0–C5 的目录与历史不变；Navigation 按 seed/navigation 独立存储于 userdata/workspaces。新 scope 不搜索/导入旧 Weapons profile；同课程后续关卡可复用自己的底盘代码。

两个启动器通过 select_workspace 选库，跨 scope 直接 unlock 拒绝。默认重启身份不依赖关卡、入口或模板版本。显式 --workspace-store 指向初始工程；同服务切到其他分组使用其 scopes/<scope> 子目录，返回原组复用原路径。显式选择已有工程不触发自动清空。

ResolvedScene重试复用定义，新建run/Core、轮状态、路程、指令时钟、传感器与Runtime；源码/revision/archive不清空。版本1存档保留，当前入口关系为c0→navigation.c0；原C5前置由 [ADR-0049](adr/0049-branching-course-progression.md)明确修订。

## 验证、取舍与开放项

决策见 [ADR-0045](adr/0045-independent-course-workspaces.md)、[ADR-0046](adr/0046-confirmed-wheel-voltage-control.md)。直接轮速隐藏电机控制，直接力矩略过电气模型，完整电气/轮胎模型增加本关负担；本次采用用户逐项确认的降阶模型。

验收包括有效闭环、零输出失败、异常日志、看门狗/限幅、惯量/方向、权限、精确结算、工程往返/重试，旧六关冻结轨迹与原生/WASM 一致性。控制曲线和 Navigation C1 理想里程计已接入，见 [34](34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md)。完整轮胎/转子接触、电感状态、独立左右轮参数及后续导航课程仍未实现。

参考：[ROS 2 差速控制器分层](https://control.ros.org/master/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html)、[WPILib 状态空间说明](https://docs.wpilib.org/en/latest/docs/software/advanced-controls/state-space/state-space-intro.html)；运行时不依赖这些框架。
