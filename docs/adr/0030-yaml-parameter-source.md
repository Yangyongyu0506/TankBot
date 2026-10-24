# ADR-0030 YAML 为游戏参数与关卡数据的可编辑源

- Status: Accepted
- Date: 2026-10-25
- Scope: 参数配置；局部扩展 ADR-0015 的单文件配置约束

## Context

用户明确要求关卡数据和可配置参数使用 YAML，禁止将数值硬编码进实现。旧配置使用 JSON，教学说明也有 Python 内置字典，容易产生重复值。

## Decision

采用 `config/game.yaml` 集中保存已有参数及关卡教学数据，`config/player-dependencies.yaml` 保存课程库规则。宿主安全解析并校验后，向 Rust/WASM 传递已有 JSON 私有 DTO。Rust/Node 测试夹具由 YAML 生成，build 自动刷新，检查工具拒绝过期副本。

JSON Schema、协议、存档和上游锁文件是接口/产物格式；不为 YAML 迁移改变其语义。代码保留数学定义和类型标识符；所有可调整数值、模型/控制系数、频率、预算及关卡阈值必须有明确 YAML 配置字段，禁止静默数值 fallback。

## Alternatives

YAML 与 JSON 各手工维护一份会漂移；给 Rust 核心增加 YAML 运行时依赖会扩大纯核心输入职责；把完整配置交给玩家 Python 会泄露私有场景。

## Consequences

构建增加一个使用现有依赖引导器的配置导出步骤。直接 Cargo/Node 前须保证夹具同步；原生运行直接读取 YAML，无需先导出。未来参数和新关卡必须同步 Schema、说明和行为验收。迁移、边界与检查见 [25](../25_ATTEMPT_RULES_AND_CONFIGURATION.md)。
