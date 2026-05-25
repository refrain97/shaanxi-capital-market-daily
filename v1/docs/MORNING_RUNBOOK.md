# V1版陕西资本市场动态总流程

目标：早上只说一句话，由 Codex 按固定流程生成“V1版陕西资本市场动态”四个频道，上传 ima，并发布网页。

## 你对 Codex 说

```text
运行 v1 早报总流程，生成今天四个版本，上传 ima，并发布网页。
```

推荐正式运行语言：

```text
运行 V1版陕西资本市场动态总流程，生成今天四个频道，完整检索并精读原文；低频频道如无内容变化，沿用上一期模板只改日期出当日图；上传 ima，并发布网页。
```

如需指定日期：

```text
运行 v1 早报总流程，日期 2026-05-12，上传 ima，并发布网页。
```

## Codex 执行顺序

1. 读取本文件和 `v1/README.md`，确认日期、四个频道和低频频道观察规则。
2. 先运行可自动化的数据脚本。日报统计窗口不是自然日当天，而是“上一交易日收盘后至本次运行日”。周二至周五默认从前一自然日开始；周一必须覆盖上周五、周六、周日至周一运行时点。脚本会自动计算该窗口，也可用 `--start-date YYYY-MM-DD` 手工指定：

```bash
bash v1/scripts/run_morning_v1.sh --date YYYY-MM-DD
```

3. 逐个频道按 SOP 生成：

- 上市公司公告早报：读取 CNINFO 数据后，必须按精读版 SOP 制作 Markdown、发布 HTML、发布 PNG；自动标题分类稿只能作为候选草稿，不能作为正式稿。
- 证券私募日报：运行 AMAC 数据脚本，生成 Markdown、发布 HTML、发布 PNG。
- 收并购日报：先观察新增/进展；有增量则更新 Markdown 和案例看板 PNG；无增量也要生成当日观察 Markdown，并沿用累计看板模板只更新日期，输出当日 PNG。
- 金融招投标清单：先观察新增/结果回溯；有增量则更新 Markdown、HTML 和 PNG；无增量也要生成当日观察 Markdown，并沿用上一期发布模板只更新日期，输出当日 HTML 和 PNG。

4. 所有四个频道的当日 PNG 就绪后，上传到 ima：

```bash
bash v1/scripts/upload_daily_ima.sh --date YYYY-MM-DD
```

5. 刷新网页归档，发布到 Vercel，并同步发布到 GitHub Pages：

```bash
bash v1/scripts/publish_v1_to_vercel.sh --date YYYY-MM-DD
```

发布脚本必须完成三段校验，任何一段失败都不得回复“已发布”：

- `v1/scripts/update_v1_index.py` 生成的 `v1/index.html` 必须包含 `YYYY-MM-DD 更新`。
- Vercel 部署成功后，必须执行 `v1/scripts/publish_v1_to_github_pages.sh --date YYYY-MM-DD`，把打包后的静态站同步到 `gh-pages` 分支；GitHub Pages 当前读取 `gh-pages`，不能只推 `main`。
- `publish_v1_to_github_pages.sh` 必须直接请求 `https://refrain97.github.io/shaanxi-capital-market-daily/v1/`，确认线上页面包含 `YYYY-MM-DD 更新`。未确认前，最终回复只能写“Pages 未确认”，不能写“已发布”。

网页入口页更新要求：

- 顶部品牌旁不显示 `V1 archive`。
- 首屏徽标只显示 `YYYY-MM-DD 更新`，不要追加流程说明。
- “最新日报”标题下不保留说明句。
- 主日报图片以缩略预览为主，不做过长的大图展示。
- 底部使用客户联系区：华泰证券西安锦业路证券营业部（西北分公司机构业务中心），联系人为机构业务中心，邮箱 `wangyue021243@htsc.com`。
- 四个频道的发布 PNG 生成后都必须加来源标识：`华泰证券西安锦业路证券营业部（西北分公司机构业务中心）` 和网页地址 `https://refrain97.github.io/shaanxi-capital-market-daily/v1/`。可直接运行 `python3 v1/scripts/brand_v1_png.py <PNG路径>`；`upload_daily_ima.sh` 在上传前也会自动补一次。

6. 最终回复必须包含：

- 四个频道的处理结果：已生成 / 沿用模板改日期 / 需要人工确认。
- ima 上传结果：成功数量、跳过数量、缺失数量；正常日缺失应为 0。
- 网页发布地址和实测结果：`https://refrain97.github.io/shaanxi-capital-market-daily/v1/` 必须已返回当天 `YYYY-MM-DD 更新`。
- 本地新增或修改的关键文件。

## 一键收尾命令

当四个频道输出已经生成完成后，可以直接执行：

```bash
bash v1/scripts/run_morning_v1.sh --date YYYY-MM-DD --finalize
```

这个命令会检查当天输出、上传已有 PNG 到 ima、刷新网页归档并发布 Vercel。若低频频道当天无新增，Codex 应先运行 `v1/scripts/render_observation_cards.py` 生成当日沿用模板图，再 finalize。

## 注意

- 低频频道没有新增时，仍需生成当日日期图片并上传 ima；内容沿用上一期模板/累计看板，不改变事实内容，不新增事件。
- 上市公司公告早报 V1 以 2026-05-20/2026-05-21 六栏精读图版为固定发布格式；正式稿必须下载/抽取高价值公告 PDF 原文、提取数字、写“今日一句话 / 重点播报 / 明日跟踪清单 / 播报收尾”，再将精读结果填入 `v1/陕西省上市公司日报v1/data/curated/listed-official-YYYY-MM-DD.json`。
- 上市公司 HTML/PNG 只能由 `python3 v1/陕西省上市公司日报v1/scripts/render_listed_official_from_json.py --date YYYY-MM-DD --png` 生成；不得用自动草稿或 Markdown 自动抽取稿发布。
- 发布前必须通过 `python3 v1/scripts/validate_v1_outputs.py --date YYYY-MM-DD` 和 `python3 v1/scripts/check_v1_responsive.py`。校验不通过时，不得上传 ima、不得发布 Vercel/Pages。
- ima 已有同名文件时，上传脚本会沿用现有去重逻辑生成带后缀的文件名。
- `v1/scripts/update_v1_index.py` 只负责历史归档；最新日报首屏文案仍由 Codex 在生成当天内容后更新。

## 检索不能缩水

每次运行都必须把检索和正文读取作为正式生产动作，不能只扫标题、不能只复用旧结论：

- 上市公司：逐公司查询 CNINFO，查询窗口为上一交易日至本次运行日；周一覆盖上周五、周六、周日至周一。对高价值公告下载 PDF，抽取文本保存到 `data/pdf-text-YYYY-MM-DD/`；关键数字必须来自公告原文。
- 证券私募：运行 AMAC 脚本；若接口发生 500/502/503/504、断连或 `IncompleteRead`，必须重试或修复重试逻辑，直到当天 JSON 生成或明确记录失败原因。
- 收并购：检索近 3-7 天公告、交易所问询/回复、重点公司名和既有案例进展；新增或变更必须回到公告原文或可信公告转引。
- 金融招投标：检索陕西招标投标公共服务平台、采购与招标网、重点主体和结果公告；必须做正文资格确认和结果回溯，不能仅凭标题排除。
