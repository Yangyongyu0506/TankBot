# ADR-0055：先验地图、私有静态障碍与局部导航

- Status: Accepted
- Date: 2026-11-11
- 相关：[C5](0054-known-map-planning-preparation.md)、[C6 规范](../43_NAVIGATION_LOCAL_AVOIDANCE.md)

## Context

C5 的公开地图同时是物理地图。C6 需要复用既有规划、定位及轮电压链，但新增障碍不能进入规划输入或通过路径校验泄漏。距离扫描必须具有独立随机流、明确采样时间和缺测制动。

## Decision

保留 `scene.walls` 为公开先验几何，在可信场景解析中生成私有静态障碍；仅 Core 适配器、扫描后端及可达性检查组合完整几何。普通 profile、地图、规划准备和管理响应不包含私有矩形。浏览器启动配置不传输已解析私有几何，可信 Authority 按同一配置重新解析。

新增 `scan2d@1`、不可变 `Scan2D` 和 `LocalControlInput`。同一导航模块顺序调用玩家 `PathFollower` 与 `LocalController`，仅最终 Twist 进入原参考链。三个输入均采用可缺失端口；缺失、错误帧或年龄大于 0.20 仿真秒时主动发布零参考，不调用局部控制器。

规划继续只依据先验网格执行一次、5 秒墙钟；固定导航与轮控制两次提交合计 12 tick。地图扫描投影只使用与扫描同采样 tick 的合法玩家 EKF，不使用最新异时位姿或真值。历史有界、跨 run/revision/source/frame 清理。

## Alternatives

- 将障碍加入公开地图：失去局部感知学习目标。
- 对玩家规划结果摆放障碍：任务依赖玩家实现，无法独立重现。
- 增加一级局部控制 Topic：增加额外提交延迟及教学负担。
- 必需输入缺失直接跳过模块：危险旧参考可能继续有效。
- 框架内置避障器：替玩家完成学习目标。

## Consequences

需要显式维护先验与物理几何边界、扫描 Schema、授权反馈和同 tick 投影。局部预测使用公开圆形安全模型，私有可达性仍使用 C5 方形栅格膨胀，两者不得混淆。30/40 ms profile 保持 experimental，模块声明不是独立 CPU 配额。本机接口隔离不承诺防设备所有者逆向。

## 实测范围

已完成本机原生两参考×3seed、Firefox/Pyodide两参考×3seed闭环、原生HTTP真实编辑升级流程、393项Python及相关Node/Rust/WASM回归。范围、失败与重跑见 [验收报告](../reports/NAVIGATION_LOCAL_AVOIDANCE_VALIDATION.md)。本状态接受C6接口与隔离设计，不升级30/40ms experimental，也不宣称其他平台或整局可靠性达标。
