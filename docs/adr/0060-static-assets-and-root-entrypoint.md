# ADR-0060 静态资源归档与根启动入口

- Status: Accepted
- Date: 2026-11-18
- Scope: 用户确认的资源/代码边界、原启动功能迁移、可重建浏览器缓存清理

## Context

关卡和配置各占根目录，消息Schema位于docs，模板只有部分Navigation已提取，Weapons等仍是Host内嵌字符串。已退役Web仍留下npm/Pyodide构建及大量Firefox缓存，源码运行入口隐藏于tools。用户要求静态游戏资源统一归assets，以根main.py启动，并确认保留协议实现、工程文档/测试、历史证据和源码历史。

## Decision

采用 [46](../46_STATIC_ASSETS_AND_ENTRYPOINT.md) 的资源布局，统一各章节模板为文件，保持原注册component、源码字节和接口。协议编解码/传输是代码，留在protocol；仅Schema及样例迁移，不修改消息ID/版本。根main.py直接执行原启动序列，删除tools/tankbot.py，不保留别名脚本或符号链接；支持Python和uv两种调用。

加载器对旧配置内的资源根进行确定映射，实际文件只有assets版本，且保留可信目录约束。玩家userdata及工程身份不迁移；环境变化需重新检查，不能复用旧Ready。缓存按可重建项审计清理，保护旧浏览器持久化存储、源码/revision与测量证据。AGENTS要求今后静态游戏资源遵守此布局。

## Alternatives

只搬levels会留下其他静态资源来源；同时移动Python协议实现会混淆数据与代码。保留两份模板/配置容易漂移；仅在根增加转发脚本不满足明确入口。删除整个.m1-cache或Firefox profile可能损失旧源码和失败记录，因此只清理识别出的可重建缓存。

## Consequences

更新加载路径、依赖摘要、检查/测试和文档链接，迁移范围较广，但物理和模板冻结基线保持。默认配置版本2.1、稳定关卡ID、Workspace scope、源码/存档格式及执行profile不变。历史报告不改写成新入口已经在过去验收；本记录修订0057/0058/0059中的资源位置和启动命令，不改变权威、部署或授权边界。
