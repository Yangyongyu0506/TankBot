# 渲染平滑、跟随相机与独立外观验收

> 本文保留配置 1.2 / 平行麦轮外观的历史显示验收。当前四轮 90° 旋转对称 X-drive 见 [新报告](OMNI_VALIDATION.md)；时间插值与相机设计继续有效。


## 范围与问题定位

日期：2026-10-22。用户要求平滑弹丸、固定世界朝向的平移跟随相机、独立 RoboMaster 风格全向外观。检查确认原来物理 60 Hz / 4 子步与 RAF 已解耦；问题是 10 Hz 视图快照直接驱动弹丸坐标，未插值。当前配置弹速为 5 m/s，因此每包约跳 0.5 m；旧设计基线 15 m/s 时为 1.5 m。此次没有改弹速或其他物理参数。

## 实施

- 视图快照独立调整为 30 Hz、轮询 33 ms；SceneTimeline 按仿真时间缓存与 lerp，车体、累计炮台角与同 ID 弹丸分别尊重采样时刻。
- FollowCamera 与显示车体共用 x/y；全局网格、墙/靶标/弹丸仅平移，世界方向固定。
- `tracked-differential-v1` 与 `mecanum-competition-v1` 独立配置，后者为四轮、镜像辊子、轮毂、甲板与蓝色装甲。未新增资产/依赖或改变碰撞几何。
- config 内部版本为 1.2；Host 裁剪公开显示参数，默认估计视图权限不变。设计与取舍见 [15](../15_RENDERING_DESIGN.md)、[ADR-0018](../adr/0018-authorized-rendering-timeline.md)。

## 自动化验证

```bash
node tests/test_rendering.mjs
python3 -m unittest discover -s tests -v
python3 docs/tools/check_design.py
node --check web/app.js
node --check web/rendering.js
git diff --check
```

9 项 JS 行为测试通过：显示帧间插值、不同网络间隔、无外推/无时间倒退、出生/消失/ID、位姿/累计关节角、估计提交延迟、相机坐标矩阵、权限/跳变清理、有界历史与独立四轮绘制。

40 项 Python 回归通过；新增检查同一执行器序列在不同显示/快照配置下 Core 输出完全相同，以及两底盘下发不同视觉配置。保留 M1/M1b 权限、Runtime、命中/冷却/重放回归。旧命中测试原先固定等待 20 tick，无法适应当前较低弹速；已改为由场景距离/配置弹速计算等待时间，没有修改期望命中数或模型参数。

## 实际浏览器

本机 Linux x86_64 / 无头 Firefox / 原生 Authority。运行各底盘真值练习页面后执行：

```bash
python3 tools/browser_smoke.py --weapons --rendering --screenshot .m1-cache/rendering-omni.png
```

全向实测：90 个连续 RAF 显示帧中，44 个相邻帧在同一快照序号下弹丸位置仍改变；页面显示 60 Hz SIM / 30 Hz VIEW / 60 FPS。持续前进与转向过程中，所有可见帧车体屏幕坐标均为 (500,350)、camera_yaw=0；车体 yaw 确实变化。差速实测相同 90 帧中有 45 个插值帧，也保持车体居中与相机 yaw=0。截图置于忽略目录 `.m1-cache/`。

默认估计视图也采集了 90 帧：车体保持居中、相机 yaw=0，弹丸显示数据始终为空，确认开火没有绕过表现权限。

工具只读取当前画面已有授权诊断数据；不从私有 IPC 读取真值来证明相机。截图经人工查看，四麦轮外观与履带外观不同，网格/墙体未随车体旋转。实际 FPS 随设备/浏览器变化，60 FPS 是本机结果，不是全平台保证。

## 边界

显示缓冲默认练习 80 ms、估计 220 ms；断流保持最后授权样本，不预测新碰撞。只收到相邻快照坐标时，lerp 无法恢复两包之间精确反弹拐点，短于快照周期的生命周期也可能不可见。未来精确回放应增加 Authority 授权轨迹关键点，而不是前端物理。旧 M1/M1b 测量报告保留其原配置/构建摘要，本报告不冒称重做 Rust/WASM 或平台沙箱验收。
