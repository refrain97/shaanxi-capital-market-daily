# 陕西资本市场日报库

本仓库用于保存 V1 日报流程、历史输出和静态网页发布文件。

## 目录

- `v1/`：四个 V1 日报流程、网页入口、脚本、数据和输出。
- `docs/`：部署、上架和运维说明，例如 `docs/DEPLOYMENT.md`。
- `index.html`、`vercel.json`：Vercel 静态站入口和路由配置。

## 日常入口

早上要跑四个 V1 流程时，可以直接对 Codex 说：

```text
运行 v1 早报总流程，生成今天四个版本，上传 ima，并发布网页。
```

具体执行清单见 `v1/docs/MORNING_RUNBOOK.md`。

日报检索窗口默认覆盖上一交易日至运行日；周一会覆盖上周五、周六、周日至周一运行时点。节假日或特殊情况可在运行命令里增加 `--start-date YYYY-MM-DD` 手工指定起始日。

## 整包迁移

生成可迁移文件包：

```bash
python3 v1/scripts/package_portable_project.py
```

产物会放在 `packages/`，解压后以 `shaanxi-capital-market-daily/` 作为静态站根目录即可访问；本地验证目录在 `dist/shaanxi-capital-market-daily/`。

## 免费 GitHub Pages 部署

本目录已经内置 GitHub Pages Actions 配置：`.github/workflows/pages.yml`。把 `shaanxi-capital-market-daily/` 作为仓库根目录推送到 GitHub 后，进入仓库的 `Settings` -> `Pages`，将 `Build and deployment` 的 `Source` 设为 `GitHub Actions`。

第一次推送 `main` 分支后，Actions 会自动运行：

```bash
python3 v1/scripts/package_portable_project.py
```

并把 `dist/shaanxi-capital-market-daily/` 发布到 GitHub Pages。发布地址通常是：

```text
https://你的GitHub用户名.github.io/仓库名/
```

根路径会自动跳转到 `v1/`。
