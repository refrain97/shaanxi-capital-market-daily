# V1版陕西资本市场动态文件夹规整

本文件说明 `v1/` 目录的固定归档方式。当前部署、脚本和网页均依赖这些相对路径，因此不移动四个频道目录，只在各目录内按职责归档。

## 总入口

- `v1/index.html`：线上网页入口。
- `v1/README.md`：项目总说明和日常运行语言。
- `v1/docs/`：总 runbook、文件夹规整说明和执行口径。
- `v1/config/`：跨频道配置，例如 ima 知识库和上传规则。
- `v1/scripts/`：跨频道通用脚本。
- `v1/assets/previews/`：网页首页预览缩略图。
- `v1/archive/`：非四个主频道的历史样例或暂存材料。

## 四个频道目录

每个主频道固定保留以下结构：

- `templates/`：SOP、配置、HTML 模板或制图口径。
- `scripts/`：该频道专用的数据抓取、渲染或处理脚本。
- `data/`：结构化数据、原始公告、PDF、PDF 抽取文本和事件库。
- `outputs/`：每日 Markdown、发布 HTML、发布 PNG、ima 上传记录。

频道目录：

- `v1/陕西省上市公司日报v1/`
- `v1/陕西省证券私募日报v1/`
- `v1/陕西省收并购日报v1/`
- `v1/陕西省金融招投标项目v1/`

## 每日输出归档规则

上市公司公告早报：

- CNINFO 数据：`data/cninfo-shaanxi-announcements-YYYY-MM-DD.json`
- 公告 PDF：`data/pdfs-YYYY-MM-DD/`
- PDF 抽取文本：`data/pdf-text-YYYY-MM-DD/`
- Markdown：`outputs/shaanxi-listed-company-morning-YYYY-MM-DD.md`
- HTML：`outputs/shaanxi-listed-company-morning-YYYY-MM-DD-publish.html`
- PNG：`outputs/YYYY年M月D日陕西上市公司早报.png`
- IMA 记录：`outputs/ima-upload-YYYY-MM-DD.json`

证券私募日报：

- AMAC JSON：`data/security-private-fund-daily-YYYY-MM-DD.json`
- Markdown：`outputs/security-private-fund-daily-YYYY-MM-DD.md`
- HTML：`outputs/security-private-fund-daily-YYYY-MM-DD-publish.html`
- PNG：`outputs/YYYY年M月D日证券私募行业动态日报.png`
- IMA 记录：`outputs/ima-upload-security-private-fund-YYYY-MM-DD.json`

收并购日报：

- Markdown：`outputs/shaanxi-ma-daily-YYYY-MM-DD.md`
- PNG：`outputs/YYYY年M月D日陕西辖区收并购事件详细案例看板.png`
- 兼容 PNG：`outputs/shaanxi_ma_cases_2026_detailed.png`、`outputs/陕西辖区收并购事件详细案例看板.png`
- IMA 记录：`outputs/ima-upload-shaanxi-ma-cases-YYYY-MM-DD.json`

金融招投标清单：

- 结构化数据：`data/shaanxi-finance-tender-projects-YYYY-MM-DD.json`，有新增或项目库更新时生成。
- Markdown：`outputs/shaanxi-finance-tender-projects-YYYY-MM-DD.md`
- HTML：`outputs/shaanxi-finance-tender-projects-YYYY-MM-DD-publish.html`
- PNG：`outputs/shaanxi-finance-tender-projects-YYYY-MM-DD.png`
- IMA 记录：`outputs/ima-upload-shaanxi-finance-tender-projects-YYYY-MM-DD.json`

## 低频频道无新增时

收并购和金融招投标即使内容无变化，也要生成当日图片：

- 收并购：运行 `python3 v1/scripts/render_observation_cards.py --date YYYY-MM-DD --type ma`，沿用累计看板内容，只更新日期。
- 金融招投标：运行 `python3 v1/scripts/render_observation_cards.py --date YYYY-MM-DD --type tender`，沿用上一期发布模板，只更新日期和累计口径。

这样网页、ima 和历史归档都保持四个频道每日齐全。

## 运行语言

推荐对 Codex 使用：

```text
运行 V1版陕西资本市场动态总流程，生成今天四个频道，完整检索并精读原文；低频频道如无内容变化，沿用上一期模板只改日期出当日图；上传 ima，并发布网页。
```
