# ADR-0023 带类型的关卡说明与 SE(3) 矩阵练习

- Status: Accepted
- Date: 2026-10-24
- Scope: C0–C2 学习体验、NumPy Runtime、C1 算法接口

## Context

用户指出初学者无法理解不透明的自定义输入/返回值，并要求所有关卡提供详细说明与 Python 类型注解；C1 应以返回 NumPy SE(3) 元素的函数解释矩阵乘法本质。

## Decision

采用逐关说明、从 SDK 声明生成的类型参考、显式注解模板、CodeMirror 提示及合成数据矩阵实验。C1 接口改为 `radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]`，返回 4×4 `T_map_radar`；框架实际左乘齐次雷达点，再发布现有目标估计。C2 复用该矩阵并只实现跟踪状态类。

NumPy 由应用预装：原生 requirements 锁定版本，浏览器 wheel 使用 Pyodide 锁与摘要验证；版本进入测试环境摘要。模板通过预览升级，只选择系统脚手架即可保留算法。详见 [19](../19_LEARNING_GUIDES_AND_SE3.md)。

## Alternatives

逐关仅给 TODO 和自定义类名缺乏教学上下文；让玩家手写网络/组织文件增加非算法负担。为当前入门范围引入完整 LSP 增加部署成本。SE(2) 3×3 适合平面，但用户已明确选用 SE(3)；采用 z=0 的标准嵌入而保持物理模型。

## Consequences

新增 NumPy 资源与启动成本，需分别验证原生和 Pyodide。提示仅覆盖已声明类型和任务参数；不作完整静态检查保证。矩阵合法性与估计准确性分离，错误估计不会纠正为真值；协议继续使用现有目标估计消息。

## Acceptance

2026-10-24：原生 80 项回归、数学/闭环与迁移专项、真实 Firefox C0–C2 流程、类型补全/矩阵实验及 NumPy 部署验收通过，证据见 [学习工具验收](../reports/LEARNING_VALIDATION.md)。接受范围为已有原生与 Firefox 本机 profile；其他平台和完整 LSP 仍待验证。当前工作区与历史证据保留，不以覆盖玩家代码完成迁移。
