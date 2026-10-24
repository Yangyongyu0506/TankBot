# 首次启动 Python 依赖验收

日期：2026-10-24。对应 [21 首次运行设计](../21_DEPENDENCY_BOOTSTRAP.md)、[ADR-0025](../adr/0025-automatic-python-environment.md)。原始环境与版本证据见 [python-bootstrap.json](python-bootstrap.json)。

## 实际起点与首启

本机 Linux x86_64、系统 CPython 3.14.4，没有 pip、ensurepip 和 NumPy；jsonschema/referencing 来自发行版，websockets 未安装。未激活开发环境，执行：

```bash
python3 tools/tankbot.py headless --level c0 --ticks 12
```

启动器自动创建项目专用的无 pip venv，下载并校验固定 pip 26.2.2 wheel，安装 requirements 及所需 binary wheel。随后自动使用新解释器继续运行，C0 达到 tick=12，rejections=[]。直接依赖实际版本为 jsonschema 4.19.2、referencing 0.36.2、websockets 17.2、NumPy 2.3.3。

启动 C0 页面服务也成功：

```bash
python3 tools/tankbot.py serve --level c0 --workspace-store .m1-cache/python-bootstrap-ui
```

实际 HTTP profile 为 C0，Workspace 可生成 18 项 SDK 类型参考；入口搜索路径未将 tools/tankbot.py 误当作 SDK。专用解释器创建的 Authority 及 Supervisor Worker 使用同一 Python 路径，Worker ready 握手报告 NumPy 2.3.3。玩家算法、消息权限与物理配置保持原样。

## 缓存、离线与恢复

- 再次执行 `headless --level c0 --ticks 12 --offline`，stdout 直接为仿真 JSON，没有安装进度；不重新安装。tick、无拒绝与同配置的物理摘要保持一致。
- 在含空格的全新临时目录复制可信 requirements、安装器锁及缓存 wheel，使用 offline=True 从零创建环境并完成真实安装；下载函数被设置为一旦调用就失败，安装仍通过。
- 同一临时环境再次准备时，将安装函数设为一旦调用就失败，复用通过。
- 安装完成后系统 Python 仍找不到 pip/ensurepip/NumPy，未进行全局或用户目录包安装。临时目录和测试 Workspace 与日常玩家项目分开。
- 安装失败不写 ready 标记，下次可重试；损坏安装器重新验证/下载、离线缓存不足和锁异常均有针对性测试。

## 自动测试

**完整 Python 回归 92 项通过**，新增 10 项引导专项覆盖：当前完整环境不写缓存、首装/复用、失败重试/玩家文件保留、依赖变更选新环境、-I 导入检查、安装器校验及缓存修复、离线安装目标约束、锁互斥/异常释放、无第三方包时的帮助/无效参数、入口与 SDK 同名、含空格参数保留。参数解析收尾后单独复跑该 10 项，全部通过。

```bash
.m1-cache/learning-venv/bin/python -m unittest discover -s tests -v
.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_python_env.py -v
python3 tools/tankbot.py --help
python3 tools/tankbot.py headless --level c0 --ticks 12 --offline
python3 tools/prepare_browser.py --offline
python3 docs/tools/check_design.py
git diff --check
```

前两条使用既有开发测试环境；实际玩家启动使用系统 python3。专用解释器和直接依赖版本记录在项目缓存 ready.json，验收 JSON 保留其路径及当前源文件摘要。文档检查、浏览器 bundle 准备及差异空白检查通过。

## 验证边界与待办

本轮实测 Linux / CPython 3.14.4。Windows Scripts/python.exe、msvcrt 文件锁及 macOS 分支需要对应平台运行证据；不因采用标准库就声明全平台通过。直接依赖固定，完整传递依赖锁与离线发行包仍属于后续打包工作。首次下载需要网络，完整缓存后可离线；不将任意玩家 import 转换为联网安装请求。
