# C2 运行中累计 RMSE 验收

## 范围与设计

2026-10-26，按用户要求将 C2 已有的累计位置 RMSE 作为运行中教学反馈展示。启用权限、标题、单位、精度和曲线容量在 levels/c2.yaml；没有按关卡 ID 选择显示行为。决定见 [ADR-0034](../adr/0034-authorized-live-evaluation.md)，接口和公式见 [18](../18_CAMPAIGN_DESIGN.md)。其他关卡继续使用终局误差规则，算法接口、物理与通关条件未改。

Authority 沿用按估计采样时刻匹配真值历史的累计平方误差，UI 只得到授权的 rmse_m 与 scored_samples。未传输位置真值、误差向量或新的机器人 Topic。无有效样本时显示等待；正常运行显示大号数值、有效样本数及有界走势，编辑器状态行同步显示。

## 自动化证据

完整 Python 回归 **163项通过**（91.370秒），新增覆盖：

- 误差为5和0时累计 RMSE 为 sqrt(25/2)，重复/倒退输出不重复计分，无匹配历史不增加有效样本。
- 未部署/空输出显示 null 而非零误差；终局值与实时值一致，结束后冻结。
- 实际移动场景的结果与独立记录的采样时刻真值一致，与错误地使用提交时刻真值的结果不同。
- 测试快照不计分，再次部署不清零，重试建立新 run 并清零。
- 其他关卡不发布 live_metrics，Python 输入和 view_snapshot 不包含该反馈；撤销可视指标 grant 后管理投影不再发布。
- 加载器拒绝未授权指标、未知指标、非法精度或历史容量，冻结基线仅明确适配后续授权/教学文字变化。

Node **3项通过**，验证空/非有限统计不冒充零误差、重复轮询去重、历史容量上限、旧报告不回退走势及新 run 清空。Schema、文档本地链接、生成夹具与 git diff --check 通过。

## 实际网页证据

Linux x86_64 / Firefox 157.0.1，分别运行原生 CPython 和 WASM/Pyodide，均为普通玩家模式：

| 检查 | 原生 | WASM/Pyodide |
| --- | --- | --- |
| 测试 Ready 后统计仍为0样本/null | 通过 | 通过 |
| 部署后运行阶段的数值、样本和曲线 | 通过 | 通过 |
| 编辑器同一累计指标 | 通过 | 通过 |
| 结束值与最终报告一致 | 通过 | 通过 |
| 重试清零、切到 C1 隐藏 | 通过 | 通过 |
| 1280/500宽度下固定视口与组件可见 | 通过 | 通过 |

[原生记录](live-rmse-native.json)、[浏览器记录](live-rmse-browser.json) 包含测试报告、活跃/终局授权状态和截图路径。截图位于 .m1-cache/live-rmse，未加入仓库。测试使用独立工作区、设置和临时存档，不修改实际 userdata。

## 复现与限制

```bash
PYTHONPATH=sdk/python .m1-cache/learning-venv/bin/python -m unittest discover -s tests -v
node tests/test_live_metrics.mjs
python3 tools/export_profile.py --check --offline
python3 tools/prepare_browser.py --offline
python3 docs/tools/check_design.py
```

UI 脚本为 tools/browser_live_metrics.py。--prepare-store 在新目录创建算法示例及临时已解锁进度；再启动独立 --player --level c2 服务、Firefox Marionette 并指定 --url/--port/--output。浏览器模式另需 --browser-qa 及本地资源缓存。

当前展示本次尝试累计误差，包含同一次尝试内多次部署；比较不同算法版本时应重试，并保持相同配置/输入条件。走势只保留 YAML 指定数量的 UI 更新点，不能作为逐样本导出或独立算法排行榜。其他 OS/浏览器仍待验证，Arena 不继承此教学反馈授权。
