# 设置、模式与存档验收

日期：2026-10-24。范围：本机原生 Authority 与浏览器 WASM/Pyodide 的设置、键盘绑定、开发者图层及玩家进度；未修改物理模型或通关阈值。

## 结果与证据

- Python：101 项回归通过，覆盖 YAML 格式/标签/重复键、原子保存与 CAS、连续解锁、重复通关、开发者不奖进度、模式撤销旧尝试、损坏存档保留、Schema、CLI/HTTP 跳关拒绝及无 Campaign 的旧沙盒模式。
- Node：3 项设置测试、7 项手柄和 11 项插值/渲染测试通过，确认改键保持底盘/执行器语义，开发者移动敌车也按显示时间插值。
- [原生浏览器验收](settings-native.json)、[浏览器 Runtime 验收](settings-browser.json)：均实际修改前进、编辑器、说明、设置键，驾驶并刷新确认保留；使用本关授权视图与普通控制接口完成 C0，存档解锁 C1，刷新后仍保留。
- 两种运行方式均验证 UI 锁住 C2、直接 start API 也拒绝；开发者进入 C2 后可开启坐标系、速度、碰撞外形等图层，独立关闭真实目标并保存。退出开发者回到玩家 C1，真值入口拒绝，C2 仍未解锁。
- 1440、1280、500 像素窗口下，设置弹窗均处于视口内，网页无滚动；截图保存在缓存，路径见 JSON。
- 新增 PyYAML 已通过现有启动器自动下载并安装到专用 Python 环境；未要求玩家手工安装。

所有 UI 验证使用独立 YAML、存档、Workspace 与 8775/8776 端口；未改变日常玩家的代码或通关文件。设备为 Linux / Firefox 157.0.1；其余平台仍待实测。

## 复现

```bash
python3 -m unittest discover -s tests -v
node tests/test_settings.mjs
node tests/test_gamepad.mjs
node tests/test_rendering.mjs
python3 docs/tools/check_design.py
```

使用全新的测试配置启动 `serve --level c0` 或 `browser --level c0 --browser-qa`，显式传入独立的 `--settings-file`、`--save-file`、`--workspace-store`；浏览器模式先运行 `python3 tools/prepare_browser.py --offline` 更新可信 bundle。本次配置复制 `config/m1.json` 后只调整 host/runtime 端口为 8775/8776。启用 Marionette 2829 的独立 Firefox 启动后执行：

```bash
python3 tools/browser_settings.py --url http://127.0.0.1:8775 --output docs/reports/settings-native.json
python3 tools/browser_settings.py --url 'http://127.0.0.1:8775/?runtime=browser' --output docs/reports/settings-browser.json
```

脚本要求新玩家存档，会修改测试配置的键位、源码存储元数据及进度；不能指向日常项目。两种模式使用不同的新测试文件。JSON 记录源码摘要，不保存 control token。

## 边界

开发者图层开关影响本机呈现，玩家 Python 的传感器 grants 与 PlayerViewSnapshot 均不扩权。玩家 C1/C2 仍需自己的算法发布地图目标。碰撞图层为几何外形，尚无接触力可视化；消息查看器仅展示现有数据，不是通用 RViz 插件系统。

浏览器通关由本机 Core Worker 通知本机存储服务；设备所有者可调试或编辑数据，此验收不宣称防作弊或服务器独立验算。存档版本迁移、多账号/云同步、远程管理员授权和 Arena 仍属后续工作。
