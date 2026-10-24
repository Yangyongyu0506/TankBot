# 教学模板升级与测试部署验收

日期：2026-10-24。范围：旧课程运行框架的升级引导、测试说明与部署按钮状态；不改变关卡通关条件或运行权限。

## 问题与处理

旧 Workspace 可以已经包含 `perception/transforms.py`，但仍使用未带版本的旧 `campaign_robot.py`。此前点击测试会在算法执行前返回 `TEACHING_TEMPLATE_UPGRADE_REQUIRED`，无法生成 Ready 报告，因此部署按钮不亮。

现在测试前展示升级预览，说明算法尚未测试。玩家确认“保留算法，更新框架并继续测试”后，创建新 revision 并继续测试。升级计划只纳入系统管理文件及缺失文件，排除已有算法与自定义测试；取消不应用升级，历史 revision 保留。系统管理文件中的自行修改会在确认后被替换，预览明确提示可从旧版本恢复。

兼容检查由 UI API 与测试共用。仅在文件前增加注释或删除版本注释，不再误报升级；语法错误进入正常文件/行号诊断。部署仍要求对应快照的 Ready 报告，页面显示禁用原因，并提供测试内容说明。

## 验证结果

- Python 回归：94 项通过，包括升级预览不修改文件、保留算法、自定义测试和历史 revision，以及升级后的真实 Ready 测试。
- [原生 Runtime 浏览器记录](teaching-upgrade-native.json) 与 [Pyodide Runtime 浏览器记录](teaching-upgrade-browser.json)：均完成旧框架 → 保存草稿 → 预览 → 取消 → 再次预览 → 确认升级 → Ready → 部署 Active。
- 两种模式均运行 3 项单元测试（2 项课程样例、1 项自定义测试）及 6 个授权传感器批次；验证部署按钮亮起、升级提示消失、修改草稿后部署重新禁用，正式画面收到估计输出。
- 逐文件比较确认已有算法、历史 `coordinates.py` 与自定义测试保持原内容。所有操作使用独立测试存储，未升级玩家实际 Workspace。
- 编辑弹窗回归通过：F2/按钮/关闭、草稿保留、焦点及游戏输入隔离；1440、1280、1024、500 像素宽度下页面无滚动。

Ready 表示接口、样例与短时间试运行通过，不代表算法完全正确或关卡通关。测试输出不进入执行器和正式渲染。

## 复现入口与限制

```bash
.m1-cache/learning-venv/bin/python -m unittest discover -s tests
.m1-cache/learning-venv/bin/python tools/browser_template_upgrade.py --prepare-store .m1-cache/upgrade-repro
python3 tools/browser_template_upgrade.py --browser-port 2829 --url http://127.0.0.1:8775
python3 tools/browser_template_upgrade.py --browser-port 2829 --url 'http://127.0.0.1:8775/?runtime=browser' --output docs/reports/teaching-upgrade-browser.json
python3 tools/browser_dialog.py --browser-port 2829 --url 'http://127.0.0.1:8775/?runtime=browser'
python3 docs/tools/check_design.py
```

浏览器脚本要求先启动相应 `serve` / `browser` 服务及启用 Marionette 的 Firefox；服务使用 `--level c1 --workspace-store <新测试存储>`。本次复制配置后仅将 `host.port` / `browser.runtime_port` 改为 8775 / 8776，Marionette 使用 2829，避免占用玩家服务。每种模式使用独立的新存储；脚本拒绝覆盖已有 HEAD。截图路径与源码摘要见 JSON 记录，截图保存在本机缓存。

已验证 Linux / Firefox 157.0.1 的两种 Runtime；未据此宣称其他浏览器、操作系统或远程 Arena 已验证。加载此次修复需重启服务并刷新页面；实际 Workspace 的升级仍由玩家预览确认。
