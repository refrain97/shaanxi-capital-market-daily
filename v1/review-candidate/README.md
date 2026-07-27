# V1 客户验收候选版

> PREVIEW · NOT PUBLISHED · 2026-07-23

本目录与正式 `v1/index.html`、四频道 `outputs/` 和发布目录完全平行，候选页面与样图均不参与日常发布。

生成与本地预览：

```bash
python3 v1/review-candidate/scripts/build_candidate.py
python3 -m http.server 8765 --directory v1/review-candidate
```

打开 `http://127.0.0.1:8765/`。样图使用 Playwright 从 `share/` 下的独立分享版页面生成，网页和分享图不共用一个超长画布。
