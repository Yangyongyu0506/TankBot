# ADR-0009 非覆盖 Workspace 与模板迁移

- Status: Accepted
- Date: 2026-10-20
- Scope: 多文件、Manifest、生成与持久化

## Context

玩家代码要跨关卡和游戏版本保留；模板解锁不能破坏已实现算法，浏览器/桌面存储能力也不同。

## Decision

采用多文件 Workspace、`tankbot.json` 和独立 Contract；模板按 ID/版本/摘要跟踪来源。任何已有文件默认不覆盖，通过独立 incoming 预览和显式合并创建新 revision。生成/迁移使用快照、CAS 和原子事务，存储适配不改变所有权规则。

## Alternatives

每关重新生成整个项目会丢积累；自动替换 TODO 或直接 AST 改写不能保证语义；单文件会限制后期软件组织。不采用静默更新。

## Consequences

需要 ledger、冲突 UI、导出备份与版本兼容窗口。玩家可编辑 Manifest，但它不是权限依据。文件路径、大小写与压缩导入需跨平台安全验证。

## Validation / Open Questions

逐字节保留已编辑文件；并发、重复迁移、中断和磁盘错误可恢复；旧项目可导出/迁移。浏览器存储后端和 SDK 兼容窗口仍待决定，见 [06](../06_WORKSPACE_AND_TEMPLATES.md)。

## 本机存储位置补充（2026-10-25）

按用户要求，玩家版本库默认改为 YAML 配置的 `userdata/workspaces/`，与个人设置及进度一起备份。旧缓存库在文件锁下非覆盖复制、校验历史后原子发布，原库保留；已有目标库优先，不合并独立项目。显式存储目录仍由 CLI 决定。未改变源码所有权、JSON revision、CAS、测试或部署语义；实现和迁移验收见 [17](../17_EDITOR_AND_DEPLOYMENT.md)。
