# ADR-0027 课程库白名单与 NumPy 矩阵

- Status: Accepted
- Date: 2026-10-25
- Scope: 玩家 Runtime 的课程依赖与 SDK 数值矩阵；细化 ADR-0008/0009/0023

## Context

用户要求只开放 NumPy 等少量基础计算库，避免直接调用封装好的机器人算法，并优先使用 NumPy 数组表示矩阵。任意宿主安装包可 import 会使教学规则不确定；C2 的当前测量集合也容易被误认为无限历史。

## Decision

采用受信配置白名单，当前唯一第三方库为 NumPy，配指定基础标准库、SDK 与 Workspace 自建模块；unittest 限于测试文件。静态检查与 Runtime 项目 loader 的导入检查共用规则；Manifest 不能自行安装包，策略纳入环境摘要。开发者模式的可视化 grant 不豁免课程依赖规则。

SE(3) 和协方差使用 float64 ndarray，SDK 在 JSON 边界扁平化协方差，现有消息形状不变。保留旧扁平协方差构造参数，读接口按用户要求改为只读二维数组，迁移说明见 [23](../23_PLAYER_CODE_AND_LIBRARIES.md)。C2 对象集合保持兼容，新增基础 `target_positions()` 转换为 `(N,2)` 数组，不实现滤波算法。

## Alternatives

自由 pip 安装可绕过算法练习且破坏跨平台一致性；单靠不安装某个库不能阻止宿主已有包；只检查 import 语句会漏掉普通动态导入。把所有对象集合转为 NumPy object 数组会混淆实体与矩阵语义。为更新矩阵接口强行改写已保存算法也不可接受。

## Consequences

需要明确库列表、可定位的错误与两平台回归；SDK 阵列比较/索引应使用 NumPy 规则，不能宣称与旧 tuple 读接口完全相同。此策略不能替代恶意 Python 的 OS 隔离、证明原创或防止设备所有者修改游戏。未来库扩展须维护者审查教学影响。

## Evidence

方向由用户明确要求；数学/导入/跨关保留测试及两种 Runtime 的真实编辑测试部署记录见 [验收](../reports/PLAYER_RUNTIME_VALIDATION.md)。原生与浏览器仍限已有本机 profile。
