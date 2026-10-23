# ADR-0021 M3 本机编辑器与部署 profile

- Status: Accepted
- Date: 2026-10-23
- Scope: EditorAdapter、WorkspaceStore 与既有 Authority 的部署适配
- Supersedes: [ADR-0003](0003-web-frontend.md) 的前端组合建议；保留 ADR-0009/0012 的所有权和生命周期原则

## Context

M1/M2 已有 Canvas、ES modules、CPython/Pyodide ModuleRunner 和共享 Authority。M3 需要真实多文件编辑与安全切换；仅引入编辑框不能证明编辑/运行隔离。没有证据要求替换现有 Renderer，独立静态网站存储也尚未验证。

## Decision

采用 CodeMirror 6、Python/JSON 扩展和可切换的社区 Vim 扩展，使用锁定的 npm 包与 esbuild，继续 ES module JavaScript/Canvas。绑定游戏焦点隔离，编辑器只保存 revision，不调用物理状态。

本机原生与浏览器 profile 共用启动器上的版本化 JSON WorkspaceStore、CAS/文件锁、非覆盖预览和导出；不回写种子目录。独立 Web 的 IndexedDB/OPFS 仍是后续部署适配。测试/部署生命周期在共享 Authority 执行，候选使用独立子进程/Worker，旧 Active 直到 tick 边界切换才结束。只允许任务授予的单模块 profile，后续图调度独立扩展。

归档记录和已保存源码跨重启保留；Ready 属于当前 Authority 会话，不能由归档或 UI 自报恢复。完整接口与支持范围见 [17](../17_EDITOR_AND_DEPLOYMENT.md)。

## Alternatives

Monaco 提供更重的 IDE 体验，但 M3 不需要语言服务器；Phaser 暂无替换现有 Canvas 的验证收益。立即迁移 TypeScript 扩大变更范围，可在更多前端模块出现后评估。IndexedDB 独立存储可脱离启动器，但需要另做配额、恢复、导出与多标签事务验证；不冒充本次已经覆盖。保存即热更无法保证多文件一致快照与失败保留。

## Consequences

新增约 1.1 MiB 未压缩编辑器 bundle；精确字节在验收记录。候选加载时浏览器有三个 Python 解释器，仍仅验证单机器人本机场景；保留 M2 的强沙箱限制。管理接口与机器人协议分离，Manifest 不成为授权来源；归档结果不用于绕过重新测试。

## Validation / Open Questions

以 [M3 验收](../reports/M3_VALIDATION.md) 的原生/真实 Firefox 流程、非覆盖/错误恢复/摘要/焦点测试为接受门。其他 OS、浏览器、独立网站持久化和服务端执行仍不在接受范围。包元数据指向 `code.haverbeke.berlin/codemirror/*`，Vim 包为 `replit/codemirror-vim`；已检查安装包类型声明与 MIT 许可证，官网访问受限不用于推断 API。
