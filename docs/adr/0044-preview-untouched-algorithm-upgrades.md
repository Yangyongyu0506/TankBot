# ADR-0044 未修改算法空模板的显式升级预览

- Status: Accepted
- Date: 2026-10-29
- Scope: 修订 ADR-0039 的旧 Workspace 升级覆盖范围；不修改 Python 接口

## Context

C3/C4 新模板与适配器已改为 tuple[PolarTargetEstimate, ...]，但旧 Workspace 中 3.0.0 的未填写 ndarray 空模板被“保留算法文件”规则排除。适配器升级到 polar_tuple@1 后检测已通过，编辑器却仍显示旧函数签名，形成源码与运行输入不一致。

## Decision

升级检测同时读取 Workspace 的受信生成 ledger。只有本关算法编辑路径、仍与某次 campaign 生成内容逐字节相同、且当前模板接口或实现确有变化的文件，才标记为 untouched generated algorithm。不能仅根据 TODO、空函数、注解或模板版本推断文件未修改。AST 比较忽略注释、空白和教学 docstring，避免跨关仅文案变化就反复要求更新。

检测和打开项目不改写源码。已有预览清单明确列出旧空模板、当前内容与新建议，用户确认后通过原 CAS apply 创建新 revision，保留历史。已修改算法不加入替换清单；缺少生成依据时按玩家内容保留。UI 不再声称这些预览完全排除 perception/ 文件。

## Alternatives

自动重写全部算法会破坏玩家代码；仅更新运行包装器留下陈旧签名；仅修改类型帮助无法改变真实源码；按 TODO 猜测未编辑可能误伤实现。本轮采用内容来源证明和已有显式预览，不新增任意代码改写机制。

## Consequences

升级提示能覆盖“当前适配器 + 旧空模板”。用户写过旧矩阵算法时，仍需按关卡说明自行迁移字段读取，不自动翻译数学逻辑。C1/C2 已写代码、关卡 ID、进度与协议不变。确认前默认保留旧源码，因此重启后需在 F2 预览并确认一次升级。

## Validation

tests/test_template_stub_upgrade.py 覆盖 C3/C4 的真实 ledger、当前适配器、旧签名、预览无写入、历史恢复、C1/C2 保留、已编辑与无 ledger 文件拒绝替换。真实默认项目只读核对发现同一原因；网页测试仅使用独立临时项目。204 项 Python 回归及原生/浏览器真实预览→确认→Test Ready 已通过，证据见 ADR-0039 的接口验收报告。
