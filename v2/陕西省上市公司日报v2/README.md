# 陕西省上市公司日报 v2

这是“陕西省上市公司日报 / 早报”的独立 V2 工作区，基线日期为 2026-06-11。

V2 当前先从 V1 完整复制今天生产日报所需的材料，不改变原有日报逻辑。后续关于“精准、准确、及时”“一级业务视角 + 二级标签”“精读兜底机制”的改进，都建议在这个目录内推进，V1 保持为稳定基线和历史参照。

## 当前目录

- `scripts/`：上市公司公告抓取、PDF 下载、日报渲染、发布页渲染、候选雷达、VR 精读选题台脚本。
- `templates/`：日报 HTML 模板、配置和 SOP。V2 默认使用 `shaanxi-listed-company-morning-report-v2.template.html`。
- `data/`：2026-06-11 的公告 JSON、PDF、PDF 文本、人工整理 JSON，以及上市公司基础清单。
- `outputs/`：2026-06-11 的早报 Markdown、发布 HTML、PNG 和 IMA 上传包。
- `docs/`：V2 迁移和后续设计记录。

## 2026-06-11 基线文件

- 原始公告：`data/cninfo-shaanxi-announcements-2026-06-11.json`
- 人工整理：`data/curated/listed-official-2026-06-11.json`
- PDF 原文：`data/pdfs-2026-06-11/`，共 43 份
- PDF 文本：`data/pdf-text-2026-06-11/`，共 43 份
- 今日早报：`outputs/shaanxi-listed-company-morning-2026-06-11.md`
- 发布页：`outputs/shaanxi-listed-company-morning-2026-06-11-publish.html`
- 图片版：`outputs/2026年6月11日陕西上市公司早报.png`
- IMA 上传包：`outputs/ima-upload-2026-06-11.json`

## 常用命令

```bash
python3 scripts/render_listed_official_from_json.py --date 2026-06-11
python3 scripts/render_listed_official_from_json.py --date 2026-06-11 --png
python3 scripts/render_vr_workbench.py --date 2026-06-11
```

## 后续改造方向

V2 的重点不是扩大公告覆盖面，而是在现有“陕西上市公司早报”的精准路线基础上，加一个更稳的选题和复核层：

- 用业务视角和二级标签辅助归类。
- 保留 PDF 精读证据，避免只靠标题关键词。
- 对没有被标签覆盖但可能重要的公告设置兜底提示。
- 让“必须精读 / 建议精读 / 底稿保留”的判断更透明，方便人工快速复核。
