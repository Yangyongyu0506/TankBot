# ADR-0002 核心语言与物理候选

- Status: Proposed
- Date: 2026-10-20
- Scope: Core 实现语言与 Physics Adapter

## Context

需要原生性能、WASM、长期维护和服务器扩展；目前仓库没有实现、基准或已验证工具链。语言偏好不能代替可行性证据。

## Decision

优先验证 Rust 与 Rapier2D，保持核心不依赖 OS 服务；Python 采用消息边界而非嵌入。备选为 C++ Host/Core 与 Box2D 的 C API。先验证运动/碰撞、CCD、原生/WASM 构建和同构建 Replay；不同时维护两套正式物理引擎。

## Alternatives

C++ 有成熟工具链和库生态，但需更强内存/ABI/并发纪律；Rust 的所有权降低部分内存风险，仍有借用学习曲线、FFI 与编译成本。自制运动学适合小探针，完整碰撞/反弹重写维护成本高。比较细节及官方来源见 [02](../02_SYSTEM_ARCHITECTURE.md)。

## Consequences

Rust 若通过验证可减少核心依赖组合；Rapier 的实际目标特性与性能需固定版本确认。物理库的确定性声明不自动变成应用级跨平台保证。

## Acceptance Gate / Open Questions

M1/M2 提交至少原生 Linux 与浏览器 WASM 的构建/600 tick/CCD/故障探针报告；Windows/macOS 后续独立验证。记录包体、启动、tick 成本、团队可维护性；若失败再试备选并记录原因。接受时锁版本与 feature，不使用浮动最新依赖。
