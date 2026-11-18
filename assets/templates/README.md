# 玩家工程模板

这些文件是**生成玩家工程的只读源码资源**，不是独立关卡脚本，也不是可部署的玩家项目。运行时不会从关卡YAML导入任意Python文件：YAML只选择引擎注册的component，再由`level_templates.py`组合文件和关卡说明。

| 目录 | 课程及职责 |
| --- | --- |
| common | Hello Robot/早期Weapons共用的被动/感知入口；Hello Robot不要求编写算法 |
| weapons | SE(3)坐标变换、KF/极坐标跟踪、装甲跟踪、预测/自瞄、系统适配器和合同测试 |
| navigation | 轮电压控制、里程计、EKF、航点/路径跟踪、全局规划、局部避障及系统适配器 |

`legacy_*`、旧pose/fusion组件保留历史模板识别及兼容用途，不表示现有关卡启用这些接口。受管适配器负责连接、验证和发布，算法文件保留TODO；这里不提供搜索、滤波或避障参考解。

过去这里只提取了部分Navigation文件，其他课程以Python字符串嵌在Host里。现已统一为UTF-8资源，经`template_resources.load_template_resource()`读取；Host中的常量名及注册component保持，模板内容逐字节一致。包初始化所需空字符串仍属于组件声明，不另造空模板文件。

生成目标目录由注册组件定义，和资源目录名无关；例如`navigation/wheel_controller.py`资源生成到玩家的`control/wheel_controller.py`。已生成的玩家代码、ledger和不可变revision不会因资源移动被改写，框架升级继续走预览/CAS/明确确认，见 [06](../../docs/06_WORKSPACE_AND_TEMPLATES.md)。
