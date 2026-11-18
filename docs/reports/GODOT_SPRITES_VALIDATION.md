# Godot预制Sprite验收

日期：2026-11-18。提交基线`782cc4a`，工作区同时包含上一轮尚未提交的UI主题改动，已保留。此轮不提交/推送，不操作日常userdata。

## 完成内容

新增`assets/sprites/industrial/`：七张透明PNG，包含绿色履带底盘、蓝色全向车壳、独立普通全向轮、炮台、炮管、装甲和靶板；两个简单SVG图标用于车头标记与弹丸。使用内置image_gen制作PNG，按用户确认的精细工业风增加金属面板、倒角、螺栓及履带/滚子纹理。靶板为米白底、红色同心圆和深色十字，不是纯红方块。提示词组与来源见 [资源说明](../../assets/sprites/README.md)。

新增`config/desktop-sprites.yaml`及Schema。资产路径、文件/像素限额、美术裁切框和弹丸最小显示尺寸集中配置。启动器仅向Godot传递可信资源路径；公共profile、机器人协议、玩家输入和权限均未增加字段。图片及裁切框不决定物理几何。

新增`sprite_library.gd`一次加载并缓存ImageTexture/AtlasTexture，生成mipmap；`vehicle_sprite.gd`装配分层Sprite2D，轮心、轮向、炮台轴、炮口和装甲壳沿用现有模型。`world_view.gd`删除坦克/靶标/弹丸即时几何画法，每帧更新节点变换，同ID复用，消失或切关释放。没有合法位姿时隐藏车体，不恢复真值。

墙体、网格、路径、估计环和局部雷达仍是授权诊断图形。现有已授权target占位使用靶板；本轮未建设新的敌车开发者图层，也未扩大敌车真值可见性。物理、评分、玩家源码/历史、存档、20ms模块声明额度及30ms原生实验性截止保持。

## 验证

| 实际命令 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_desktop.py -v` | 最终14项通过：旧配置默认、非法主题、缺失资产、PNG透明通道/容量/裁切范围及生命周期 |
| `.m1-cache/learning-venv/bin/python -m unittest discover -s tests -p test_rendering.py -v` | 3项通过：显示配置不改物理、独立底盘和敌车开发者权限 |
| `python3 tools/check.py --suite godot --offline -- --headless` | 修复编译后81项通过，证据`.m1-cache/godot-qa/20261118T111148640668`；当时尚未加入最终裁切框及转轴专项断言 |
| `python3 tools/check.py --suite godot --offline -- --disable-vsync` | 最终86项通过，证据`.m1-cache/godot-qa/20261118T111757773085`；裁切前/中间81项成功记录也保留 |
| `python3 docs/tools/check_design.py` | 文档/链接、Schema、样例及代码片段检查通过 |
| `python3 tools/export_profile.py --check --offline` | 生成Core配置一致，未重生成或修改物理夹具 |
| `git diff --check` | 通过 |

真实窗口为Linux X11/OpenGL、Godot4.7.2、NVIDIA RTX5070 Laptop GPU，1440×900。执行图片加载/复用、90°轮组标定、靶板绑定、底盘/炮台独立转动、炮口尺寸、消失/缺姿态/重载清理、Navigation隐藏武器。继续完成C1真实保存文件→Start→检查/运行→Space开火→权威通关，C0键盘驾驶、重试、Navigation/Weapons往返及源码/revision/ledger保留。F2使用记录型启动器，未声称本轮人工操作了真实VS Code。

双底盘对比图使用独立显示夹具：只有公开模型和合成授权消息，为展示细节调整视宽；不是正式关卡、物理闭环或玩家输入。C0截图来自实际关卡流程。全部验收使用临时设置、进度、工作区、XDG和随机端口。

## 截图

- [真实C0：履带坦克与同心圆靶板](assets/godot-sprites/game-c0.png)
- [双底盘与靶纹细节：隔离显示夹具](assets/godot-sprites/game-sprites.png)
- [C1实际运行](assets/godot-sprites/game.png)
- [任务说明](assets/godot-sprites/game-guide.png)

## 修正过程及限制

首轮无头流程因Sprite辅助函数把父节点过窄标为Node2D、实际传入Control而编译失败，工具等待超时。改为只需add_child的Node合同后通过；为验收工具补充超时输出落盘，保留`.m1-cache/sprite-qa/headless.log`和`parse-first.log`。初版桌面测试还曾因测试块错位出现NameError，修复后14项通过。

首次窗口发现生成PNG的近透明杂点扩大了自动非透明包围框，导致炮管/装甲变细。只读检查alpha后，把美术裁切范围写入YAML；未改写生成PNG，也未更改模型尺寸。最终窗口已复验炮管长度、分层和实际画面。文档初查在本报告创建前发现缺失链接，补齐报告后重新检查。

继续使用既有`--disable-vsync`测试选项；此前默认VSync问题未在本轮解决或改变生产默认。未运行全套标准回归、无关物理基准或WASM；没有修改Core。本轮证据不覆盖Windows/macOS、其他分辨率、完整十三关GUI、独立Godot导出打包或Runtime长期可靠性；30ms profile保持experimental。

## 文件

新增资源、提示词说明、`config/desktop-sprites.yaml`、`docs/schemas/desktop-sprites.schema.json`、`sprite_library.gd`、`vehicle_sprite.gd`及本报告/截图。修改Godot主入口/世界显示/集成测试、`desktop.py`及配置/Schema、桌面测试、Godot验收工具、文档检查器、44规范和文档/Schema索引。此前主题改动及历史报告保留。
