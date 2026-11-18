# 工业风 Sprite 提示词组

来源：内置`image_gen`，非CLI/API脚本。全部生成使用transparent_background=true；无用户参考图片。下列共同约束和逐资产要求组成制作提示词组。target最终来自追加的比例编辑，其余使用首轮结果。美术方向由用户确认：精细工业风，保留绿/蓝配色。

## 共同约束

```text
Use case: stylized-concept. Asset type: production-ready transparent PNG 2D game sprite for TankBot.
Strict orthographic top-down, front points RIGHT. Detailed polished industrial game art,
rounded/chamfered silhouettes, machined metal panels, precise seams, small bolts and subtle wear.
Readable silhouette at small game scale. Entire isolated component visible, centered,
small transparent padding. No perspective, floor, scenery, cast ground shadow, text or logos.
Genuine transparent background.
```

## 逐资产要求

| 资产 | 提示要求 |
| --- | --- |
| `tracked_base.png` | Green tracked tank CHASSIS ONLY, no turret/cannon. Horizontal 4:3 silhouette; two straight graphite caterpillar tracks, individual tread pads and steel roller caps. Sage-green beveled hull, ventilation, panel seams, countersunk bolts. Symmetric top/bottom. |
| `omni_hull.png` | Blue compact square CENTER HULL/DECK only, no wheels/turret. Chamfered shell, inset metal deck and four diagonal supporting arms at 45/135/225/315 degrees, 90-degree symmetric layout. Sky-blue armor, brushed grey metal, vents and recessed bolts. |
| `omni_wheel.png` | SINGLE conventional omni wheel, NOT mecanum. Horizontal long axis, about 2.5:1. Seven transverse steel/rubber rollers with axes across image y; no 45-degree mecanum stripes. Rounded graphite silhouette, silver hubs, dark end caps. Neutral greyscale. |
| `turret.png` | TURRET CAP ONLY: circular low-profile metal cap, centered pivot, no barrel/protruding parts. Central hatch, concentric rim, recessed bolts, ventilation seams. Neutral pale-grey steel/graphite for green/blue tint. |
| `barrel.png` | SINGLE horizontal cannon tube, breech LEFT/muzzle RIGHT, about 8:1. Rounded/chamfered ends, pale machined steel, dark muzzle aperture, three collars and fine seams. No turret or tank. |
| `armor.png` | SINGLE horizontal 4:1 armor strip. Rounded graphite frame, pale orange/red inset strip with three segments, two end fasteners and restrained bevel highlights. |
| `target.png`初稿 | Square rounded/chamfered dark-grey plate, four corner bolts, warm ivory face, red/off-white concentric circles, dark bullseye and thin black crosshair. Light wear; no numbers, text or stand. |

## 靶板最终编辑

先查看本地初稿，再以该图作为唯一edit target，使用precise-object-edit：

```text
Preserve the industrial rounded/chamfered metal rim, four corner bolts, ivory face,
red/off-white CONCENTRIC CIRCLES and thin black crosshair. Change ONLY the overall board
aspect to a horizontal 4:3 rectangle (width exactly 1.333 times height), so it matches
a 0.8 m by 0.6 m simulation target. The rings must remain true circles, NOT stretched
ellipses; expand the board's left/right ivory area and rim instead of stretching the rings.
Strict orthographic overhead, centered, small transparent padding on all sides.
Entire rectangle visible, no perspective, no shadow, no text. Genuine transparent background.
```

最终PNG按原样保存，不以Python补画或重绘纹理。车头和弹丸SVG属于简单图标，直接编写矢量源，运行时同样加载为共享纹理。
