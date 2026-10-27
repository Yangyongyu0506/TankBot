# ADR-0039 类型化极坐标观测集合

- Status: Accepted
- Date: 2026-10-27
- Scope: 局部修订 ADR-0035/0038 的 PolarTracker Python 输入；不改变通信协议

## Context

C2 的 Tracker 输入为 tuple[TargetEstimate, ...]，C3 曾改用 NumPy (N,2) 矩阵表达原始极坐标。用户要求 C3 统一为 tuple[PolarTargetEstimate, ...]，避免同时改变测量坐标与对象读取方式。C4 复用同一算法，因此同步适配。

## Decision

PolarTracker.update 接收 measurements: tuple[PolarTargetEstimate, ...]、own_pose: NDArray[np.float64]、dt: float，返回 PolarTargetEstimate | None。每个输入对象直接保存该帧 Radar 的 range_m/bearing_rad，covariance 为 None；已确认的测量噪声矩阵仍由构造参数提供。当前长度为 0/1，空帧为 ()，不累计历史，不提供实体 ID，不预先滤波或变换坐标。

观测对象集合使用 tuple；内部状态、Jacobian、协方差等数值矩阵仍用 NumPy。C5 匿名装甲数组和其他 SDK/线上消息形状不改。C3/C4 的 Python 脚手架升至 5.0.0，保留所有玩家算法文件及历史，玩家按文档自行适配旧二维下标。

管理适配器声明静态 scaffold_api，框架升级通过 AST 检查版本，不执行源码，也不以注释或协议端口类型代替 Python 接口检查。仅检查本关仍引用同一管理入口的适配器，不限制高级自定义入口。缺少声明的旧适配器需预览升级；语法错误仍交给正常 Python 测试日志。

## Alternatives

保留数组无法满足统一接口要求；自动重写玩家算法可能破坏已有实现。让新函数继续收到旧数组只修改注解会产生误导；因本次接口与线上消息相互独立，需要分别版本化。为单个对象集合建立 NumPy object 数组没有数值计算收益。

## Consequences

C2→C3 的主要变化成为 x_m/y_m 到 range_m/bearing_rad，而非集合操作方式变化。类型帮助与 indexed tuple 补全需同步；旧矩阵算法必须显式适配，不承诺无修改兼容。协议、权限、物理、关卡判定和 C4 控制权不变。

## Validation

依据为用户明确要求。实际 tuple/空帧/字段值/不可变/采样时序、升级保留与类型提示测试位于 tests/test_weapons_curriculum.py、tests/test_sdk_hints.mjs；闭环与最终结果见 [接口验收](../reports/POLAR_TUPLE_VALIDATION.md)。
