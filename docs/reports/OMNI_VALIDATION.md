# 四轮旋转对称全向底盘验收

## 范围与确认

日期：2026-10-22。用户明确要求四组轮子每 90° 绕中心旋转对称，并回复“符合”，确认固定普通全向轮、对角 X、轮心半径 R=0.25 m、轮半径 r=0.10 m。实施依据为 [ADR-0019](../adr/0019-fourfold-omni-wheel-layout.md)，取代旧平行麦轮几何。

保留差速模型、车体质量/惯量、0.8×0.6 m 圆角矩形碰撞体、受限力/力矩伺服、阻力、观测频率与武器冲量约定。此次更改轮组几何与运动学观测，不新增轮电机/滑移/轮地接触动力学。显示轮组位于既有车体碰撞包络内；车体仍采用其既定矩形碰撞包络。

## 实现与唯一数据源

- config/m1.json 版本 1.3：wheels.omnidirectional 使用 radial_omni@1，四轮 name/azimuth_deg 与 R 只配置一次；旧 mecanum_half_length/width、roller_angle_deg 已移除。
- Core 的 wheels.rs 根据实际车体 vx/vy/wz 计算切向轮速，仍按子步梯形积分累计角。理想观测不读取玩家估计。
- 仓库 Python 参考里程计按名字及同一标定反解，不再调用旧麦轮公式。玩家持久 Workspace 未被读写迁移或覆盖。
- Host 校验四轮唯一、等间隔 90°、正半径和显式模型版本，公开 wheel_calibration 经过独立 Schema；不携带真实位姿。
- Renderer 从相同标定派生轮心与安装角，四组轮子真正旋转安装；使用普通全向轮的横向滚子，删除麦轮斜辊纹与平行轮组。视觉配置保留独立甲板/轮毂/装甲样式，不复制轮心数据。

## 运动学验收

`qdot_i=(-sinα_i*vx+cosα_i*vy+R*wz)/r`，正轮轴径向向内。纯前进时两轮正、两轮负；正 yaw 时四轮同号。默认轮序 front_left/front_right/rear_left/rear_right 的 α 为 45°/315°/135°/225°。

[测试](../../tests/test_omni.py) 用独立写出的四行矩阵检查纯 vx、vy、wz 和混合运动，并验证：反解误差 ≤1e-10；按名重排不变；改变 R/统一安装偏角后轮速随之改变，车体动力学不变；重复名/非等距/缺项/错误版本同时被 Host/Core 拒绝。既有差速与全向 600 tick 测试继续通过。

实测数据为 [omni-baseline.json](omni-baseline.json)，包含配置、原生/WASM 摘要及额外 600 tick 前进＋横移＋转向闭环、位姿误差、拒绝数和全执行器同构建重放结果。本次 600 tick 混合运动最大位置误差 0.00063815 m、最大 yaw 误差 0.00024557 rad，98 次估计提交、无拒绝；完整同构建重放一致，原生/WASM 第一轮探针差为 0 rad/s。该测量不作为跨硬件位级确定性保证。原 M1/M1b 与渲染报告保留旧模型/配置的历史证据，不用它们替代本次验收。

## 浏览器验收

真实无头 Firefox/原生 Authority：模型 ID 为 radial-omni-x-v1，画面人工检查显示四个不同安装朝向的全向轮；90 个 RAF 帧中 44 个相邻帧在快照序号不变时弹丸仍移动，页面为 60 Hz SIM / 30 Hz VIEW / 60 FPS。前进/转向时车体居中、相机 yaw=0；单发与授权视图测试通过。截图为本机忽略文件 `.m1-cache/radial-omni-x.png`。

JS 数值/绘制测试核对四轮半径、径向与滚动方向正交、轮心及朝向随 90° 旋转映射到另一组、实际 Canvas rotate 调用、轮径由标定派生，并保留时间插值/相机/生命周期回归。

## 复现与限制

```bash
python3 tools/build.py
cargo test --locked
python3 -m unittest discover -s tests -v
node tests/test_rendering.mjs
python3 docs/tools/check_design.py
python3 tools/build.py --wasm
node tools/wasm_probe.mjs
python3 tools/measure_omni.py
python3 tools/tankbot.py serve --chassis omnidirectional --view weapons-practice
```

本轮 46 项 Python、9 项 JS、10 项 Rust 测试通过。原生/WASM 额外执行同一公开标定轮速探针；完整浏览器 WASM/Pyodide 与服务器隔离仍未实现。普通 Python 子进程仍仅供本人可信代码。

旧 1.2 配置须显式迁移到 1.3；旧麦轮玩家算法需按新几何版本调整。不会自动覆盖玩家代码，也不虚构旧麦轮模型仍可运行的兼容层。JointState/Twist 结构与单位保持，模型版本与正轴标定必须匹配。
