# ADR-0033 独立 YAML 关卡与注册组件

- Status: Accepted
- Date: 2026-10-25
- Scope: 五个既有关卡的架构重构，不改变玩法与协议

## Context

用户要求关卡是配置。当前数据已参数化，但模板、UI、校验、列表和评分仍耦合关卡身份；同一关卡分散在多个 profile。审计与冻结基线见 [27](../27_LEVEL_PLUGIN_ARCHITECTURE.md)。

## Decision

将五关各自组合写入自包含 YAML，用统一受限加载器、安全 Schema 和少量稳定组件注册解释。沿用 Core 与既有通信/模块/Workspace 边界，编译为现有 DTO。规则和指标声明式配置，信息授权在 Authority 执行，UI 显示偏好服从授权。局部修订 ADR-0030 的关卡存储位置：通用模型与预算仍在 game.yaml，关卡数据改为独立文件；其余 YAML 参数源约束不变。

## Alternatives

只拆配置文件仍保留 ID 分支不能支持零代码扩展；任意脚本插件扩大信任边界；重写物理或构建大量未来组件超出范围。仅提取现有实际能力。

## Consequences

需要严格交叉校验和自动发现/构建索引；玩家源码、稳定 ID、成绩和已确认物理必须保持。YAML 不具备代码加载能力；新组件类型仍需引擎实现和对应验证。

## Acceptance

已完成冻结基线、权限、生命周期、旧源码/存档及临时插件验收，并在 Linux/Firefox 上完成原生及 WASM/Pyodide 五关真实 UI 通关，见 [迁移验收](../reports/LEVEL_PLUGINS_VALIDATION.md)。接受范围限于已有组件和已验证平台，不代表未来模型、多机器人或服务器强隔离已经实现。
