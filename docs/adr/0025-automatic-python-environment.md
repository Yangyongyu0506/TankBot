# ADR-0025 启动前自动准备应用 Python 环境

- Status: Accepted
- Date: 2026-10-24
- Scope: CLI 引导、应用依赖、Host 与本机 Worker 解释器

## Context

用户直接运行 C0 遇到 NumPy 缺失提示，要求首启自动安装。当前系统还没有 pip/ensurepip。第三方库若在引导前导入会阻断自修复；仅向 Host sys.path 添加包又不能解决使用 -I 的玩家子进程。

## Decision

标准库启动器先解析参数、检查依赖，缺失时创建项目私有 venv，从固定并校验 SHA-256 的官方 pip wheel 引导，安装仓库 requirements，验证后以专用解释器重新运行同一命令。版本/平台/路径变化使用独立环境，安装串行化；重复启动复用缓存，并提供 --offline。

完整已有环境可直接使用，不修改调用者的 Python。安装只读取可信仓库依赖，不读取玩家 Manifest 或 Workspace 的安装要求；仿真及 Runtime 内不安装。详见 [21](../21_DEPENDENCY_BOOTSTRAP.md)。

## Alternatives

继续要求玩家 pip install 无法满足首次运行体验；系统安装、--user 或强制修改受管理 Python 会干扰宿主。仅用 site-packages/PYTHONPATH 无法覆盖隔离子进程。依赖额外 uv/conda 或手动安装 ensurepip 会增加安装前提；接受 stdlib venv 加固定 wheel 的引导成本。

## Consequences

首次需要网络或完整离线 wheel 缓存，缺少匹配 binary wheel 时明确失败；不隐式编译系统库。环境及下载文件占用磁盘，保留旧环境以支持并行进程。完整传递依赖锁与其他平台发行仍待验证。

## Evidence / Acceptance

本机 CPython 3.14.4 在没有 pip、ensurepip、NumPy 的状态下首启 C0 成功，专用环境内玩家 Worker 可导入 NumPy；同一命令启动 HTTP 与缓存离线复用成功。92 项 Python 回归、含安装/重试/锁/隔离/路径与入口遮蔽的专项检查通过，另有离线新环境实装。见 [验收报告](../reports/PYTHON_BOOTSTRAP_VALIDATION.md)。接受当前引导设计，Windows/macOS 分支不作为本轮已完成平台验收。
