# V2 Unified Publish Dashboard

这是 Investment OS V2 的统一发布看板包，也是后续 GitHub Pages 推送的唯一网页入口。

包含：

- `index.html`：总控看板。
- `data/dashboard_state.json`：统一展示数据。
- `reports/*.html`：每个自动化时点的公开摘要报告。

展示内容：

- 今日运行状态和权限边界。
- 08:30-15:30 自动化时点。
- 最新公开报告。
- 数据 coverage / stale 摘要。
- draft / formal registry 状态。
- shadow / observe_only 观察状态。
- 需要用户确认的动作或风险队列。
- 本地完整报告落点。

权限边界：

- 本包是脱敏发布包，不包含原始行情、完整账户文件或正式交易记录。
- 页面展示结论默认是 `数据观察 / shadow only`。
- draft / shadow / watch / watch_low_sample 不获得 `trigger / position / risk_gate` 权限。
- 没有用户确认，不得把建议动作写成已执行。

## 生成数据

```bash
python3 投资框架v2/09_代码与自动化/scripts/build_v2_publish_dashboard.py
```

准备下一交易日空白时点，同时保留历史报告：

```bash
python3 投资框架v2/09_代码与自动化/scripts/build_v2_publish_dashboard.py --date 2026-07-09 --prepare-next-session
```

## 本地预览

推荐使用统一脚本：

```bash
python3 投资框架v2/09_代码与自动化/scripts/serve_v2_dashboard.py
```

打开：

```text
http://127.0.0.1:8765/index.html
```

## GitHub Pages

将本目录作为 Pages 包推送即可。自动化脚本 `run_v2_hourly_automation.py` 每次运行后会重建 `data/dashboard_state.json`。
