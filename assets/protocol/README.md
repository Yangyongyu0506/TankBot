# 协议静态资源

[examples](examples/README.md)保存TankBot消息、合同、Workspace和管理接口的规范示例。消息结构由同级assets中的 [schemas](../schemas/README.md)定义；Schema `$id`、协议字段和版本不因磁盘位置变化而修改。

根目录`protocol/tankbot_protocol/`是Python编解码、领域验证及Transport实现，属于代码，不应迁入此目录。本文与样例不引入ROS2/DDS依赖。正文规范见 [03](../../docs/03_PROTOCOL_SPECIFICATION.md)，目录/入口约定见 [46](../../docs/46_STATIC_ASSETS_AND_ENTRYPOINT.md)。
