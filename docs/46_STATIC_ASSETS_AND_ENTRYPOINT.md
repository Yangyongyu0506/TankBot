# 46 静态资源布局与根启动入口

## 目的与现行边界

统一游戏静态资源与明确源码启动入口；不改变课程、物理、消息接口、玩家源码或存档。用户确认边界见 [ADR-0060](adr/0060-static-assets-and-root-entrypoint.md)。游戏可变数据不属于assets，测试冻结证据、历史报告和构建元数据仍属于工程资料。

| 原位置 | 当前位置 |
| --- | --- |
| levels | assets/levels |
| templates及Host内嵌源码字符串 | assets/templates，包含common/weapons/navigation |
| config | assets/config |
| docs/schemas | assets/schemas |
| docs/examples | assets/protocol/examples |
| examples/robot | assets/examples/robot |
| tools/tankbot.py | main.py，旧文件已删除 |

地图/Sprite保持原assets目录。协议Python实现仍在`protocol/tankbot_protocol/`，不是资源。运行时生成的玩家contracts/Manifest、代码、revision/ledger/history及存档留在各自userdata工程，不能搬入静态资源树。

## 模板与加载接口

35个注册组件及十三关的稳定ID、课程参数、前置和Workspace scope保持。原有27段Host内嵌程序提取为UTF-8文件，与既有7份Navigation模板统一；模块常量仍作兼容绑定，实际源码仅来自资源文件。空包文件由注册声明生成。

`load_template_resource(name)`仅允许注册代码使用的`目录/文件.py`形状，拒绝路径逃逸及链接出界；YAML不能指定任意可执行脚本。迁移前后逐项校验组件文本、教学说明注入后源码、starter Python及传给Rust的Core输入摘要。受管框架版本和文件内容不变，因此资源移动本身不要求玩家应用模板升级。

Schema/协议示例统一从新路径读取，`$id`、消息shape和协议版本保持。桌面Schema允许旧`config/...`引用，加载器仅将旧资源根映射到assets中的实际文件，不保留第二份配置。旧自定义配置内的levels/config引用继续解析；配置、底盘和Runtime profile仍各自执行可信目录约束。绝对外部关卡目录及用户自定义配置保留原支持方式。

目录变化会改变部署环境摘要：旧会话的Ready/可执行产物不能冒充新环境，应重新Start检查；这不改源码revision、ledger、历史或正式进度。游戏不读取或重写日常userdata来完成迁移。

## 启动、开发命令与缓存

`main.py`直接拥有原参数解析→依赖准备→Host/Godot启动流程，不通过runpy、symlink或导入旧工具脚本转发。`python3 main.py`与`uv run main.py`使用同一个requirements/自动准备逻辑；uv不是第二套游戏依赖管理器。原`--level`、`--map`、设置/存档/Workspace覆盖、headless/probe及离线参数保持。

```bash
python3 main.py
uv run main.py
python3 main.py --help
python3 tools/check.py --offline
```

浏览器退役后的可重建缓存可删除：node_modules、npm缓存、旧Web/Pyodide构建、浏览器页面/启动/编译缓存。保留测量JSON/日志/截图、历史报告、旧源码与版本库；Firefox持久化idb/ls/OPFS等不按缓存盲删。日常userdata、原生Python/Godot工具链和独立Rust WASM能力不受清理影响。

## 验收与限制

验收须覆盖模板/物理输入冻结摘要、旧配置引用及目录安全、十三关加载、协议结构、跨关源码/存档兼容、Python及uv入口、独立Godot流程、统一检查和生成配置一致性。不以目录重组宣称新增平台支持、OS沙箱或Runtime可靠性；运行profile继续experimental。历史报告保留当时命令与结果，只把本地链接调整到资源新位置。
