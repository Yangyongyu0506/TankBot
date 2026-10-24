# M3 Editor and Deployment 验收

## 范围与结论

2026-10-23，Linux x86_64 / CPython 3.14.4 / Firefox 157.0.1 / Node 22.22.1。本机 M3 的多文件编辑、模板、Manifest、快照测试、部署与失败恢复已实现并验证。详见 [实现接口](../17_EDITOR_AND_DEPLOYMENT.md)、[浏览器记录](m3-browser.json) 与 [原生 UI 记录](m3-native-ui.json)。原生与浏览器复用同一 DeploymentManager，不改变已确认物理模型。

## 路线图逐项证据

| M3 交付/验收 | 实现与证据 |
| --- | --- |
| CodeMirror、多文件、Python/JSON、Vim | 锁定 npm 依赖、本地 bundle；真实 Firefox 编辑/保存/切换文件与焦点检查 |
| 持久化 Workspace | 源码/ledger revision、原子 HEAD、线程/文件锁、CAS；刷新后文件恢复；导入/导出与历史预览 |
| 非覆盖模板与迁移 | 三栏预览、默认 keep、显式 incoming 新 revision；原 revision 保留；并发与磁盘失败测试 |
| Manifest / Module Contract | 当前单周期模块 profile；真实生成的 M3 JSON 夹具；拒绝 SDK 遮蔽、越界连线、系统位姿请求与不匹配合同 |
| Edit 不改变 Active | 真实 UI 在新建/修改/保存/测试时检查 Active 的 artifact 和实例保持原样 |
| Test 与 Deploy 同一摘要 | 报告绑定 revision、源码清单、Core/SDK/Schema/配置/平台；未测试或环境变化拒绝部署 |
| 测试路径隔离 | 子进程/独立 Pyodide Worker 执行 import、unittest 与 6 个授权传感器仿真批次；测试输出不提交 World |
| 失败保留旧版本 | 语法、导入、死循环、单元测试、错误 frame、候选被杀等负例；旧 Active 不被替换 |
| 成功切换与回滚 | 算法 tick 边界切换；新 publisher/实例、旧队列清理；同一 run_id，世界 tick 前进；回滚使用历史 artifact 的干净 Runtime |
| 焦点隔离 | Vim 编辑焦点发送 W/J/L/Space 后，控制按键未激活，观测位姿/炮台/开火计数不变 |
| 记录与恢复 | 测试/部署结果与 artifact 源码归档可导出；新会话不能把归档伪装成 Ready |

## 实际检查

- `python3 -m unittest discover -s tests -v`：61 项通过，包括 8 项新增 Workspace/部署测试；未把继承导致的重复用例计作额外覆盖。
- `npm run build`：CodeMirror/Vim bundle 与完整第三方许可证生成成功，精确字节/摘要见 JSON 报告。
- `node tests/test_rendering.mjs`：既有渲染时间线、相机、两底盘与弹丸插值回归。
- `node tests/test_wasm.mjs`：两底盘各 600 tick 的原生/WASM 完整私有快照一致性回归；这些私有检查不在正式 UI/Runtime 中运行。
- `python3 docs/tools/check_design.py`：链接、Schema、示例及 ADR 状态一致性；不能代替上述运行测试。
- `git diff --check`；根 AGENTS.md 未修改。

真实 UI 使用独立 `.m1-cache/m3-*-*` 测试库，未修改玩家种子或 `examples/robot`。复现步骤：

```bash
npm ci --ignore-scripts
npm run build
python3 tools/prepare_browser.py --offline
python3 tools/tankbot.py browser --workspace-store .m1-cache/m3-browser-probe --browser-qa
# 另启 Firefox --headless --no-remote --marionette，使用独立测试 profile
python3 tools/browser_m3.py
# 停止 browser 服务后，以 serve 和独立 store 验证原生模式
python3 tools/browser_m3.py --url http://127.0.0.1:8765 --output docs/reports/m3-native-ui.json
```

脚本操作真实编辑器、按钮与 API，记录测试摘要、两次激活、失败测试、显式回滚、World tick 连续性、源码刷新持久化及归档数量。截图保存到报告列出的 `.m1-cache/*.png`，可供本机复核，生成缓存不提交。报告中的 profile/源码/资源摘要界定证据范围，旧 M2 报告保留为历史证据。

## 许可证与取舍

直接依赖锁定 CodeMirror `6.0.2`、Python 扩展 `6.2.1`、JSON 扩展 `6.0.2`、Vim `6.4.0`、view/state/commands 及 esbuild `0.28.2`，传递依赖与 integrity 在根 package-lock.json。已检查安装包 MIT 许可证/声明与当前 repository 元数据：CodeMirror 指向 [维护仓库](https://code.haverbeke.berlin/codemirror/view)，Vim 用法参考[扩展维护者说明](https://github.com/replit/codemirror-vim/tree/master/packages/codemirror-vim)。官网文档读取受限；实际 API 通过已安装版本的类型声明、构建与浏览器验证，不把旧 GitHub 镜像当活跃上游。

继续使用 Canvas/ES modules，未引入 Phaser/TypeScript 全仓迁移；决策见 [ADR-0021](../adr/0021-editor-and-deployment-profile.md)，替代原先整套前端候选 ADR-0003。底盘、炮台、弹丸、后坐/碰撞和传感器参数没有变化。

## 明确限制与后续

仅验证本机 profile。原生仍只运行本人可信代码；普通 Python 子进程不构成服务端沙箱。浏览器继承独立 origin/CSP/Worker 强制终止，但没有硬内存配额或反设备所有者作弊能力。其他 OS/浏览器、独立 Web 存储、强服务端沙箱仍需专项验证。

当前是单周期模块、多源文件；完整 Module 图属于 M5。Test 的仿真部分观察当前授权传感器流，不是另开一个由候选控制的完整比赛，不能证明控制策略或所有工况的正确性。初始化预算、批次预算与文件/存储限额均在 config/game.yaml。归档是观察记录，不是跨会话部署凭证；关闭页面可能来不及归档最后结果，但已保存 revision 不受影响。磁盘回收/云同步/断电与其他平台文件锁验证后续进行。

下一阶段为 M4 的 C0–C2 教学内容；先共同确认 Radar 等新增传感器模型及关卡能力策略，再实现任务配置与渐进接管。M3 不隐含授权新的物理模型。
