# Repository Guidelines

## 项目状态与阅读入口

TankBot 处于 Design & Documentation 阶段，当前只有技术文档、Schema、夹具和文档检查工具，没有游戏、SDK 或 Runtime 实现。新任务先读 [文档索引](docs/README.md)、相关领域设计及 [ADR 状态表](docs/adr/README.md)，再按 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 确定范围。不得把 Proposed 技术或示例版本视为已验证功能。

## 必须遵守的架构规则

1. 开始任务先检查现有文件与相关设计，不盲目覆盖已有工作。
2. 遵守当前 Accepted ADR；Proposed 的接受需要验证证据。
3. 不随意修改核心职责或依赖边界；重大变化新增/更新 ADR 并同步规范。
4. 保持已发布协议向后兼容；破坏性变化必须明确升级版本，见 [03](docs/03_PROTOCOL_SPECIFICATION.md)。
5. 玩家程序不得直接访问 Ground Truth、World 对象或宿主引擎句柄。
6. UI 不得绕过 View Policy；授权裁剪在 Authority 侧执行，见 [04](docs/04_STATE_AND_VIEW_MODEL.md)。
7. 玩家估计不得修改真实物理状态；执行器输入必须经过授权与仲裁，连续速度使用 cmd_vel Topic，离散操作才考虑 Command。
8. 新模块遵守 [Module Contract](docs/05_ROBOT_MODULE_SYSTEM.md)，声明类型、生命周期、频率、依赖、预算与错误处理。
9. 修改公共接口时同步修改文档、Schema、样例及相关测试；实现缺失的测试明确标待办。
10. 重大架构变更必须留下 Context、Alternatives、Consequences 和明确状态，不能仅修改代码。
11. 不直接覆盖玩家 Workspace 源码；模板与迁移必须非覆盖、可预览、可恢复，见 [06](docs/06_WORKSPACE_AND_TEMPLATES.md)。
12. 接口语义、消息形状与命名优先参考 ROS 2 习惯，见 [ADR-0014](docs/adr/0014-ros-style-velocity-interface.md)；不引入 ROS2/DDS 运行时依赖，不建设不必要的通用中间件。
13. 架构清晰优先于过早优化；优化以基准为据，不能把前端物理变成权威。
14. 不为快速实现绕过身份、权限、沙箱、配额或固定 tick 提交边界，见 [07](docs/07_SIMULATION_DESIGN.md)、[08](docs/08_RUNTIME_AND_SECURITY.md)。
15. 优先跨平台与可测试性；按平台验证后声明支持，不承诺跨硬件位级一致。

## 组织、检查与贡献

文档使用中文，标识符/文件名用英文；设计正文在 `docs/`，决策在 `docs/adr/`，结构/夹具在 `docs/schemas/` 和 `docs/examples/`。实现目录建议见 [02](docs/02_SYSTEM_ARCHITECTURE.md)，尚未创建的目录不是现有代码。使用空格缩进和语言惯例；选定语言后再提交 formatter/linter 配置。

文档检查命令为 `python3 docs/tools/check_design.py`（需现有 `jsonschema`/`referencing` 环境）；另查 `git status --short`、`git diff --check`。领域安全与游戏测试尚未实现，不能用文档检查代替，详见 [验证计划](docs/12_VALIDATION_AND_OPEN_QUESTIONS.md)。引入实现后在根 README 写明真实 build/test/run 命令。

现有 Git 历史仅有初始化提交，尚无稳定约定；采用简短祈使句提交主题，如 `Add protocol schema fixtures`，每次提交聚焦一个目的。PR 说明问题、变化、相关 issue、实际验证及限制；可见界面变化附图。不得提交凭据、本机环境文件、私有回放或生成垃圾。
