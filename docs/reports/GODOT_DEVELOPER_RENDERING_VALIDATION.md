# Godot开发者实体透明度与诊断顺序验收

日期：2026-11-18。基于`307142c`及上一轮尚未提交的设置/开发者显示实现继续修改；保留这些工作及旧验收报告，没有提交、推送或操作日常`userdata/`。

## 用户确认与实现

用户确认开发者实体统一50%不透明度，墙体和障碍保持现状。涵盖己方授权/真值坦克、差速和全向敌车、靶标与弹丸；车辆底盘、炮台、轮组、装甲均包含在内。参数取`config/desktop-tools.yaml`的`rendering.developer_entity_opacity`，玩家模式恢复不透明显示。

`vehicle_sprite.gd`由Node2D改为CanvasGroup，先合成车辆零件，再使用self_modulate调整整体透明度，避免零件交叠处变为更不透明的区域。该行为使用 [Godot CanvasGroup文档](https://docs.godotengine.org/en/4.7/classes/class_canvasgroup.html) 所述原生合成，不改贴图或物理。system选中位姿与已开启的真值车体不重复叠画；玩家估计与真值作为两个独立显示来源保留。

`rendering.draw_order`分地图填充、实体和顶层诊断三个区间，由Schema保证顺序不颠倒。公开目标估计/Radar绘图移至诊断节点；公开和开发者坐标轴、点、速度、碰撞轮廓均在实体上方。原始地图、安全网格和私有障碍填充仍在底层，不跟随点线一起覆盖车体。动态生成的敌车/弹丸不依赖节点创建顺序；所有显示仍受原View Policy和独立开发者grant约束。

## 实际检查

| 命令 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_desktop.py -v` | 16项通过；新增拒绝透明度越界和绘制顺序倒置的配置测试 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 195项通过，证据`.m1-cache/godot-qa/20261118T142155545714/flow.json` |
| `python3 tools/check.py --suite godot --offline -- --disable-vsync` | 196项通过，证据`.m1-cache/godot-qa/20261118T142252494075/flow.json` |
| `python3 docs/tools/check_design.py` | 160份Markdown、1447个本地链接、29份Schema，以及夹具和代码片段检查通过 |
| `python3 tools/export_profile.py --check --offline` | 生成Core配置一致，退出码0 |
| `git diff --check` | 通过 |

真实流程包含开发者切入C0、发射弹丸、进入差速敌车关和全向小陀螺关，确认实体透明度与合成节点、动态弹丸低于公开/私有诊断层、地图填充低于实体。额外一项真实窗口检查读取坦克内部坐标轴像素，确认轴线保留自身颜色而未被底盘或炮台遮住。原有改键/CAS、C6扫描与同tick投影保护、撤权、源码/历史/进度保留及VS Code文件→Start→Weapons.C0通关流程继续通过。

窗口为Linux X11/OpenGL、Godot4.7.2、NVIDIA RTX5070 Laptop GPU、1440×900。验收采用隔离设置、存档、工作区、XDG与随机端口；F2使用记录型编辑器启动器。没有更改生产VSync设置。

## 截图

- [Hello Robot.C0：半透明坦克、靶标、弹丸与顶层坐标轴](assets/godot-developer-rendering/game-developer-translucent-target.png)
- [差速敌车](assets/godot-developer-rendering/game-developer-translucent-differential.png)
- [Weapons.C4：四向全向敌车与观测点](assets/godot-developer-rendering/game-developer-weapons.png)
- [Navigation.C6：扫描点、地图填充及私有障碍](assets/godot-developer-rendering/game-developer-navigation.png)

## 范围与限制

修改Godot世界/车辆/开发者/诊断显示、设置流程测试和桌面配置测试，以及desktop-tools YAML/Schema、44/22规范和ADR-0059当前决定。未改Core、Authority、Runtime、协议、关卡数据或玩家源码。本轮不重复运行上一轮410项全量Python和18项Rust回归；未跑独立WASM或长期性能基准。Linux窗口通过不代表Windows/macOS、其他分辨率或发行包已验收；Runtime profile仍为experimental，原预算及固定提交门不变。
