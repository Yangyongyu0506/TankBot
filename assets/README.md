# TankBot 静态资源

此处存放与玩家存档、可变运行状态无关的游戏数据。不得写入玩家代码、revision、日志、依赖安装缓存或构建产物。玩家工程始终属于`userdata/`。

| 目录 | 用途 |
| --- | --- |
| [levels](levels/README.md) | 独立YAML关卡插件；稳定ID、前置、教学文案、规则与权限 |
| [templates](templates/README.md) | 玩家算法空模板、受管适配器和项目测试的源码资源 |
| config | 游戏/桌面/运行profile、底盘、依赖白名单与默认设置 |
| [schemas](schemas/README.md) | JSON Schema；消息、合同、Workspace及配置结构 |
| [protocol](protocol/README.md) | 协议数据样例，不包含编解码器或Transport实现 |
| [maps](maps/README.md) | 共享静态地图 |
| [sprites](sprites/README.md) | 预制Sprite及外观标定 |
| examples/robot | 独立SDK示例工程，不是玩家日常源码库 |

协议实现仍在根目录`protocol/tankbot_protocol/`，裁判与Runtime在各自代码目录。根入口为`python3 main.py`或`uv run main.py`。设计与兼容规则见 [46](../docs/46_STATIC_ASSETS_AND_ENTRYPOINT.md)。
