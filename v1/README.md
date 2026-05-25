# V1版陕西资本市场动态

本目录保存“V1版陕西资本市场动态”的完整生产流程。四个频道独立归档，SOP、模板、脚本、数据和输出各归其位；网页入口、ima 上传和发布脚本放在 `v1/` 公共层，后续迭代 V2 时可以并行保留。

日常目标：早上只需一句运行指令，由 Codex 完成四个频道的检索、原文精读、制图、ima 上传和网页发布。

## 目录分类

- `index.html`：V1 网页入口，必须保留在 `v1/` 根目录。
- `README.md`：V1 流程索引和日常使用说明。
- `docs/`：总流程 runbook、文件夹规整说明和执行口径。
- `config/`：跨流程配置，例如 ima 知识库和上传规则。
- `scripts/`：跨流程通用脚本，例如网页发布、ima 上传、归档刷新。
- `assets/`：网页使用的轻量资源，例如首页预览缩略图。
- `archive/`：非四个日报主流程的历史样例或暂存归档。
- `陕西省上市公司日报v1/`、`陕西省证券私募日报v1/`、`陕西省收并购日报v1/`、`陕西省金融招投标项目v1/`：四个主流程目录。

更多细则见：`v1/docs/FILE_ORGANIZATION.md`。

## 检索和精读硬要求

V1 不是轻量标题监控，不能为了省时间或省 token 缩水检索。每天必须按频道 SOP 做完整搜索、正文读取和数字核验：

- 上市公司公告早报：逐公司抓 CNINFO，统计窗口为上一交易日至本次运行日；周一必须覆盖上周五、周六、周日至周一运行时点。下载/抽取高价值公告 PDF 原文，正式稿必须写公告原文中的金额、比例、期限、股数、表决权、到期融资等关键数字。
- 证券私募日报：以 AMAC 公示接口为主，生成结构化 JSON，再从 JSON 生成 Markdown/HTML/PNG；接口异常要重试，不能用旧数据冒充新数据。
- 收并购日报：即使今日无新增，也要做近 3-7 天公开检索和既有重点案例进展复核；出现新增案例、状态变化、金额/比例变化、问询回复或终止事项时必须读公告正文后更新看板。
- 金融招投标清单：必须按“发布主体 + 产品词 + 服务词 + 语义动作词”组合检索，读取公告正文/PDF/OCR或可信详情页，并做结果回溯；不得只按标题含不含“证券/承销”判断。

## 低频日报运行约定

除陕西上市公司公告早报外，低频频道默认先走“观察环节”，避免每天把全年底稿、长窗口列表或大体量 JSON 放进模型上下文。

适用频道：

- 证券私募行业动态日报
- 陕西辖区收并购市场动态看板
- 陕西金融类招投标项目清单

观察环节只读取最近 3-7 天候选、上一期累计摘要和差异清单。若无新增事件、无重大进展、无待核验高价值线索，则记录“观察无新增”，并使用上一期发布模板/累计看板更新为当日日期，生成当日 PNG，上传 ima，保证四个频道每日都有当日图片；有增量时再进入正式日报/看板更新环节。

## 01 陕西上市公司公告早报

目录：`v1/陕西省上市公司日报v1/`

- `templates/`：V1 SOP、配置、HTML 模板。
- `scripts/`：CNINFO 逐公司公告抓取脚本，主入口为 `fetch_cninfo_shaanxi_announcements.py`。
- `data/`：陕西上市公司池、CNINFO 公告数据、公告 PDF 和抽取文本。
- `outputs/`：每日底稿 Markdown、发布 HTML、发布 PNG 和 ima 上传记录。

核心检索规则：不得只使用 CNINFO 全市场分页后本地过滤；必须用陕西公司池逐公司查询 `stock=证券代码,orgId`，并在主窗口外至少回溯5个自然日做高价值公告补漏。

正式发布硬约束：

- 上市公司早报正式版只能走固定链路：`data/curated/listed-official-YYYY-MM-DD.json` 精读结构化数据 -> `scripts/render_listed_official_from_json.py` -> HTML/PNG。
- `scripts/render_listed_publish.py --auto-draft` 只能生成候选草稿；`--official-from-md` 已禁用，不得作为正式稿。
- 精读 JSON 必须填满固定版式：4 个 KPI、4 个业务机会、4 条重大事项、4 个动态卡片、5 条资本运作、2 组固定披露清单、6 个跟踪项。
- 发布前 `v1/scripts/validate_v1_outputs.py` 会检查 CNINFO/PDF 原文、精读 JSON、正式模板标识、KPI 类名、自动截断省略号和机械抽取数字；不通过不得上传或发布。

## 02 证券私募行业动态日报

目录：`v1/陕西省证券私募日报v1/`

- `templates/`：V1 SOP。
- `scripts/`：AMAC 数据抓取与 Markdown 生成脚本。
- `data/`：2026-05-07 原始 JSON。
- `outputs/`：2026-05-07 底稿、HTML、发布 PNG 和 ima 上传记录。

## 03 陕西辖区收并购市场动态看板

目录：`v1/陕西省收并购日报v1/`

- `templates/`：V1 SOP 和配置。
- `scripts/`：长图渲染脚本。
- `outputs/`：2026 年详细案例看板 PNG。

## 04 陕西金融类招投标项目清单

目录：`v1/陕西省金融招投标项目v1/`

- `templates/`：V1 SOP。
- `data/`：结构化项目库和发布主体观察池。
- `outputs/`：Markdown 底稿、发布 PNG 和 ima 上传记录。

核心检索规则：低频高价值项目按“发布主体优先、标题语义复核、正文资格确认、结果回溯更新”处理；无新增时保留观察记录，并用上一期模板更新日期生成当日图。

## 约定

- `templates/` 保存流程定义和可复用模板。
- `scripts/` 保存可执行脚本。
- `data/` 保存生成样例所依赖的结构化数据。
- `outputs/` 保存已生成的底稿、HTML、PNG 和上传记录。

## 每日激活指令与完成标准

每天要让 Codex 完整跑 V1 流程时，直接复制下面这句话即可：

```text
运行 V1版陕西资本市场动态总流程，生成今天四个频道，完整检索并精读原文；低频频道如无内容变化，沿用上一期模板只改日期出当日图；上传 ima，并发布 Vercel 和 GitHub Pages。发布完成前必须直接检查 https://refrain97.github.io/shaanxi-capital-market-daily/v1/ 返回今天 YYYY-MM-DD 更新。
```

如需指定日期，把“今天”换成具体日期：

```text
运行 V1版陕西资本市场动态总流程，日期 YYYY-MM-DD，生成四个频道，完整检索并精读原文；低频频道如无内容变化，沿用上一期模板只改日期出当日图；上传 ima，并发布 Vercel 和 GitHub Pages。发布完成前必须直接检查 https://refrain97.github.io/shaanxi-capital-market-daily/v1/ 返回 YYYY-MM-DD 更新。
```

Codex 最终回复前必须完成并报告以下检查结果：

- 四个频道当天文件齐全：Markdown、应有的 HTML、PNG、ima 上传记录。
- 上市公司公告早报：CNINFO 逐公司检索完成，PDF 原文已下载/抽取，高价值事项数字来自公告原文。
- 低频频道：已完成公开检索和既有案例/项目回溯；若无新增，明确写“沿用模板只改日期”；若有进展，更新看板或项目库。
- ima 上传：`uploaded + skipped` 覆盖四个频道，`missing=0`；上传记录必须为 `uploadStatus: success`，不能只看命令是否跑完。
- Vercel 发布完成。
- GitHub Pages 发布完成：`gh-pages` 分支已更新，并且线上地址 `https://refrain97.github.io/shaanxi-capital-market-daily/v1/` 实测包含当天 `YYYY-MM-DD 更新`。
- 线上关键链接可访问：四个频道当天 HTML/Markdown/PNG 和首页预览图应返回 HTTP 200。

不能只推 `main` 或只发布 Vercel 后就回复“已发布”。GitHub Pages 当前读取 `gh-pages` 分支，必须经过 `v1/scripts/publish_v1_to_github_pages.sh` 同步并完成线上日期校验。

推荐完整收尾命令：

```bash
bash v1/scripts/run_morning_v1.sh --date YYYY-MM-DD --finalize
```

如遇节假日或需要人工指定窗口，可显式指定起始日：

```bash
bash v1/scripts/run_morning_v1.sh --date YYYY-MM-DD --start-date YYYY-MM-DD
```

若四个频道产物已经手工生成齐备，也可以分步收尾：

```bash
bash v1/scripts/upload_daily_ima.sh --date YYYY-MM-DD
bash v1/scripts/publish_v1_to_vercel.sh --date YYYY-MM-DD
```

其中 `publish_v1_to_vercel.sh` 会自动刷新首页归档、发布 Vercel、同步 `gh-pages`，并检查 GitHub Pages 线上日期。

## 网页发布步骤

早上需要完整运行“V1版陕西资本市场动态”四个频道时，直接对 Codex 说：

```text
运行 v1 早报总流程，生成今天四个版本，上传 ima，并发布网页。
```

更明确的正式运行语言：

```text
运行 V1版陕西资本市场动态总流程，生成今天四个频道，完整检索并精读原文；低频频道如无内容变化，沿用上一期模板只改日期出当日图；上传 ima，并发布网页。
```

Codex 执行清单：`v1/docs/MORNING_RUNBOOK.md`。

四个 V1 流程产出当天文件后，统一回写入口页 `v1/index.html`：

- 最新日报区：展示当天最重要的一份日报，并保留其他频道入口。
- 日报频道区：更新每个频道的最新日期、数量或关键指标。
- 历史归档区：新增当天条目，链接到对应 HTML、Markdown 和 PNG。
- 首屏徽标只保留 `YYYY-MM-DD 更新`，不要恢复 `V1 archive` 或流程说明字样。
- 最新日报标题下不放说明句；主日报预览图保持缩略展示，避免在网页端和手机端过长。
- 页面底部保留客户联系信息：华泰证券西安锦业路证券营业部（西北分公司机构业务中心），联系人为机构业务中心，邮箱 `wangyue021243@htsc.com`。
- 所有 V1 发布 PNG 生成后必须加来源标识：`华泰证券西安锦业路证券营业部（西北分公司机构业务中心）` 和网页地址 `https://refrain97.github.io/shaanxi-capital-market-daily/v1/`。统一执行脚本为 `python3 v1/scripts/brand_v1_png.py <PNG路径>`；`upload_daily_ima.sh` 上传前会自动执行一次。

确认当天最新日报区已更新后，从仓库根目录执行：

```bash
bash v1/scripts/publish_v1_to_vercel.sh --date YYYY-MM-DD
```

发布脚本会先运行 `v1/scripts/generate_v1_previews.py` 和 `v1/scripts/update_v1_index.py`，自动扫描四个频道 `outputs/` 并重建历史归档；随后发布 Vercel，再调用 `v1/scripts/publish_v1_to_github_pages.sh` 同步 `gh-pages` 并检查线上 GitHub Pages 日期。一般不需要手工维护归档列表。

发布脚本同时会执行正式模板与响应式硬校验：上市公司早报如缺少精读 JSON、误用简易模板、首页 KPI 兜底、或手机/桌面出现横向溢出，流程会直接失败。

当天 PNG 上传 ima 可单独执行：

```bash
bash v1/scripts/upload_daily_ima.sh --date YYYY-MM-DD
```

当四个频道输出已经齐备，也可以一键收尾：

```bash
bash v1/scripts/run_morning_v1.sh --date YYYY-MM-DD --finalize
```

发布地址固定为：

```text
https://refrain97.github.io/shaanxi-capital-market-daily/v1/
```

## 正式访问统计

当前 V1 已接入正式统计注入流程，统计配置在 `v1/config/analytics.json`，注入脚本为 `v1/scripts/inject_analytics.py`。现在配置仍是未启用状态；填入 Umami Website ID 并启用后，可以统计首页访问、单篇 HTML 日报访问、打开日报、下载 Markdown/PNG、复制分享链接、历史归档筛选和搜索等行为。

趋势看板样板页：`v1/analytics-dashboard-sample.html`。

详细设计见：`v1/docs/ANALYTICS_PLAN.md`。
