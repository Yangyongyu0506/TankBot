# ADR-0049 公共入门与双主线进度树

- Status: Accepted
- Date: 2026-11-03
- Accepted: 2026-11-04
- Scope: 九关进度与关卡选择，不改变玩法、算法合同、物理或工作区身份

## Context

Navigation 使用独立项目、不复用 Weapons 代码，但旧入口要求通关 Weapons C5，造成两条不同学习目标之间的路线阻塞。当前 ApplicationState 已按显式 prerequisites 判断全部前置，存档支持按目录顺序记录非连续完成集合；旧文档仍有“连续前缀”，加载器又不允许前置出现在后面的展示位置，界面只有线性下拉框。

用户明确确认唯一公共 c0，以及 Weapons c1→c2→c3→c4→c5 和 Navigation navigation.c0→navigation.c1→navigation.c2 两条独立主线；两条首关均以前者 c0 为唯一硬前置。

## Decision

YAML metadata.prerequisites 为唯一解锁定义，数组表示全部完成。仅将 navigation.c0 的 [c5] 改为 [c0]，其他边不变。稳定ID、文件名、章节和 metadata.order 保持；order 只负责展示及既有存档序列化，不隐含权限。未知前置与环继续拒绝，但不因前置的展示位置靠后而拒绝合法无环图。

原生、浏览器、本机存储与CLI共用 ApplicationState 检查；锁定错误列出缺少的具体前置。保留玩家/开发者和地图练习语义。版本1存档不迁移、不伪造完成、不在读取时重写，旧链式存档与非连续完成集合均可读取。

目录公开 prerequisites/order/description，UI由目录生成公共入口、章节分列、节点与实线依赖，展示完成/可挑战/锁定/当前状态，锁定节点仍可查看详情。通关展示所有新开放节点，不自动跳到唯一下一关。两条补充练习仅为教学文案，不另建推荐或权限系统。

campaign/navigation 独立工程沿用ADR-0040/0045，切换只选择对应库，保留源码、revision、ledger及历史，旧测试/部署随Authority/Worker销毁。不复制跨主线算法、不赠送参考解。

## Alternatives

全部自由选关会破坏同主线代码依赖；保留Weapons通关门槛与独立工程无关；按章节/编号推断权限会产生第二套规则；增加更多独立分支会让已解锁任务缺少前序算法。本轮均不采用。

## Consequences

需新增树形选择UI与公开目录元数据，调整旧链式文案、正式存档Schema及回归。窄屏分组纵排、图内滚动，保持页面固定视口与编辑器流程。局部修订ADR-0026的全局链式顺序、ADR-0046与文档33的Weapons C5→Navigation入口描述；ADR-0033的数据驱动原则与ADR-0045工作区隔离继续有效。历史验收报告保留当时事实，以新设计说明当前规则。

## Acceptance Gate

用户已确认设计。分支/旧档/非连续集合、API/CLI、目录未知/环/展示顺序、scope往返与源码历史回归已通过；完整Python回归263项通过，Node界面回归13个文件通过。在独立玩家存档中，原生与浏览器均实际完成公共c0、打开两分支、进入Navigation再回Weapons，没有开发者绕过或预填完成记录。证据、界面及Linux/Firefox验证范围见 [验收报告](../reports/BRANCHING_PROGRESSION_VALIDATION.md)，设计见 [36](../36_BRANCHING_PROGRESSION.md)。原有物理与单关教学难度不在本次变更范围内。
