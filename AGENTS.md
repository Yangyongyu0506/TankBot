# Repository Guidelines

## 项目状态与阅读入口

TankBot 已有 Rust 权威仿真、Python SDK/Runtime、Web 编辑器与两种本机运行方式。当前课程由 `levels/*.yaml` 自动发现；真实范围、平台证据及限制以 [文档索引](docs/README.md) 和 [路线图](docs/10_DEVELOPMENT_ROADMAP.md) 为准。新任务先读相关设计及 [ADR 状态表](docs/adr/README.md)，检查 `git status`，保留已有修改；不得把 Proposed 或历史报告视为当前已验证功能。

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

文档使用中文，标识符/文件名用英文；设计在 `docs/`，决策在 `docs/adr/`，Schema/夹具在 `docs/schemas/` 和 `docs/examples/`。实现位于 `core/`、`host/`、`runtime/`、`sdk/python/`、`web/`；课程在 `levels/`，公共模型和参数在 `config/`，地图在 `assets/maps/`。新增参数写入对应 YAML。使用空格缩进及现有风格；Rust 使用 rustfmt。

本地与CI共用 `python3 tools/check.py`；普通前端测试由 `npm test` 自动发现，构建后另跑 `npm run test:wasm`，真实网页另跑 `npm run test:browser -- --help` 查看运行分组。构建和运行命令见根 README；文档检查不代替权限、调度、迁移或玩家流程回归。收尾运行 `git diff --check`。使用隔离存档/工作区验收，勿操作日常 `userdata/`。

提交主题参考近期 `git log`，每次聚焦一个目的；未经用户要求不提交或推送。PR 说明问题、变化、实际验证及限制，可见界面变化附图。区分跨平台构建与完整玩家流程验证；不得提交凭据、本机环境、私有记录或构建缓存。
