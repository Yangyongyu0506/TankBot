# ADR-0047 Navigation 里程计与授权控制反馈

- Status: Accepted
- Date: 2026-11-03

> 现行解读（2026-11-10）：原批次预算描述记录当时共享字段；[0053](0053-backend-runtime-execution-profiles.md)已将声明准入与整批墙钟拆分。模块额度、采样/输入、固定6tick和评分保持，当前合同见 [41](../41_RUNTIME_EXECUTION_PROFILES.md)。

## Context

用户批准先补 C0 控制调试，再新增 C1 里程计，并逐项确认接口、阈值、理想传感器和显示权限。只看 C0 终点误差不足以解释控制响应；直接复用系统自身位姿会绕过里程计教学。

## Decision

用可配置、受独立信号权限限制的曲线显示参考 Twist、编码器 FK、左右轮速与生效电压；采样时钟、容量及图例由 YAML 声明，Authority 有界记录，UI 轮询不会丢掉中间样本。不从 Ground Truth 计算曲线反馈。

新增声明式 `navigation.c1`，同一 Navigation 项目保留 WheelController，只增加 `Odometry(model,initial_pose).update(wheel_rates_radps,dt)->NDArray[np.float64]`，返回地图系 `[x,y,yaw]`。沿用理想 30 Hz 编码器、10 Hz 模块、6 tick 提交和原电机；两个模块共用原批次预算。

只公开初始位姿，正式车体/相机使用玩家候选，经 Pose Selector 和 View Policy 显示；Python 不得到当前系统位姿。私有评分按估计采样 tick 匹配真实自身位姿，运行中只显示分别授权的累计位置/朝向 RMSE。

24 秒固定指令末同时检查原运动两条件及用户确认的 0.15 m / 0.10 rad RMSE、至少 100 次有效估计。规则、显示和教材在独立 YAML；系统脚手架改变走预览，已有算法和历史不覆盖。具体接口与约束见 [34](../34_NAVIGATION_ODOMETRY_AND_FEEDBACK.md)。

## Alternatives

直接显示真实速度会破坏信息语义；仅在浏览器轮询时采样会漏掉控制切换。让玩家自己处理 JSON/发布和文件创建增加无关负担。先增加噪声/融合会同时引入过多难点。上述方案均未采用。

## Consequences

复用原 Core、协议、模块图、存储和渲染，无新增运行依赖。新增评分源、规则事实、多指标显示与独立控制信号授权均为通用能力，不按关卡 ID 分支。30 Hz 传感器在 10 Hz 算法中取最新样本存在积分近似；终局不等待未提交批次，精度标准承认这些边界。强服务端沙箱及后续课程不属于本轮。

## Validation

Accepted 记录用户确认的设计边界；实现、测试结果和本机平台限制见 [验收报告](../reports/NAVIGATION_ODOMETRY_VALIDATION.md)。
