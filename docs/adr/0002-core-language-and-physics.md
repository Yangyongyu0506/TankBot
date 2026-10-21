# ADR-0002 核心语言与物理候选

- Status: Proposed
- Date: 2026-10-20
- Scope: Core 实现语言与 Physics Adapter

## Context

需要原生性能、WASM、长期维护和服务器扩展；M0 时仓库没有实现、基准或已验证工具链。语言偏好不能代替可行性证据。

## Decision

优先验证 Rust 与 Rapier2D，保持核心不依赖 OS 服务；Python 采用消息边界而非嵌入。备选为 C++ Host/Core 与 Box2D 的 C API。先验证运动/碰撞、CCD、原生/WASM 构建和同构建 Replay；不同时维护两套正式物理引擎。

## Alternatives

C++ 有成熟工具链和库生态，但需更强内存/ABI/并发纪律；Rust 的所有权降低部分内存风险，仍有借用学习曲线、FFI 与编译成本。自制运动学适合小探针，完整碰撞/反弹重写维护成本高。比较细节及官方来源见 [02](../02_SYSTEM_ARCHITECTURE.md)。

## Consequences

Rust 若通过验证可减少核心依赖组合；Rapier 的实际目标特性与性能需固定版本确认。物理库的确定性声明不自动变成应用级跨平台保证。

## Acceptance Gate / Open Questions

M1/M2 提交至少原生 Linux 与浏览器 WASM 的构建/600 tick/CCD/故障探针报告；Windows/macOS 后续独立验证。记录包体、启动、tick 成本、团队可维护性；若失败再试备选并记录原因。接受时锁版本与 feature，不使用浮动最新依赖。

## M1 Evidence / Status Review

M1 已用 Rust 1.99.1、rapier2d-f64 **0.36.1**（enhanced-determinism、serde-serialize，依赖摘要见 Cargo.lock）实现本机两底盘/接触/传感器，并完成 Linux 原生和 wasm32-unknown-unknown 的同核心构建、Node 中 600 tick WASM 执行、原生重放和 Runtime 故障探针。见 [实际报告](../reports/M1_VALIDATION.md)。下载公开镜像只解决本机工具链获取，不构成平台保证。

Status 继续 Proposed：M1 的实验性实现可以使用候选组合，但原接受门包含完整浏览器 WASM 部署；当前浏览器页面连接的是原生 Host，尚无双 Worker/Pyodide 验证。高速弹丸 CCD、发布包体、Windows/macOS 及长期维护成本仍待后续阶段，不能因为一组浮点结果相同就宣称跨平台位级确定。

## M1b 补充证据（2026-10-22）

[武器验证报告](../reports/M1B_VALIDATION.md) 已覆盖本机高速弹丸/互撞、旋转刚体查询、冲量、原生/WASM 同探针和真实浏览器操作。高速弹丸的初步接受门已有证据；完整浏览器双 Worker、生产包体与 Windows/macOS 构建仍未满足，Status 保持 Proposed。
