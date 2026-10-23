# ADR-0003 Web 前端组合

- Status: Superseded
- Date: 2026-10-20
- Scope: 表现、编辑器和桌面 UI 候选
- Superseded by: [ADR-0021](0021-editor-and-deployment-profile.md)，基于 M3 的 Canvas/CodeMirror/Vim 实证；以下保留原提案背景。

## Context

需要跨平台表现、可视化与多文件 Python 编辑。前端游戏框架通常自带时间/物理，需要明确限制职责。

## Decision

建议 TypeScript + Phaser 实现场景和渲染，CodeMirror 6 实现编辑器，可选 Vim 扩展。RendererAdapter 只读 PlayerViewSnapshot；Phaser update 仅用于表现。面板框架、图表库和桌面壳暂不冻结，Tauri 为研究候选。

## Alternatives

原生 Canvas 依赖少，适合最小探针但需自行管理场景；PixiJS 可作为表现备选；Monaco 编辑能力丰富但应比较包体和多文件成本；完整 Unity/Godot Web UI 不符合当前 Web 编辑器优先方向。

## Consequences

通过适配器隔离编辑器与 Renderer，便于替换；需要验证编辑器焦点、Vim 与游戏快捷键冲突、Worker/包体成本。不能将前端物理用于评分。

## Acceptance Gate / Open Questions

M2/M3 对多文件编辑、错误定位、Vim、Canvas/WebGL、不同浏览器做探针与许可证/版本审核；查明 CodeMirror 当前包/仓库来源，不能把已迁移的 GitHub 镜像当活跃仓库。官网抓取受限不是完成验证。依据与来源见 [12](../12_VALIDATION_AND_OPEN_QUESTIONS.md)。
