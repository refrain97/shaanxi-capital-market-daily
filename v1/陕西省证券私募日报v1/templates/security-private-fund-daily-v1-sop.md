# 证券私募行业动态日报 V1 制作流程

版本：V1  
适用场景：每日监测全国证券私募重点动态、陕西证券私募今年以来动态，以及办公地在陕西的证券私募管理人新产品备案。  
默认输出：Markdown 底稿、可编辑 HTML、发布 PNG、原始 JSON、ima 上传记录。

## 1. 固定数据源

主数据源均为中国证券投资基金业协会信息公示系统：

- 私募基金管理人分类查询公示：`https://gs.amac.org.cn/amac-infodisc/res/pof/manager/managerList.html`
- 已注销私募基金管理人公示：同一管理人分类查询页面下方“已注销私募基金管理人”
- 私募基金公示：`https://gs.amac.org.cn/amac-infodisc/res/pof/fund/index.html`

接口口径：

- 新增管理人：`/amac-infodisc/api/pof/manager/query`
- 注销管理人：`/amac-infodisc/api/cancelled/manager`
- 新备案产品：`/amac-infodisc/api/pof/fund`

注意事项：

- 协会列表接口使用 `size=20`，小尺寸请求可能返回 500。
- 协会接口偶发 500/502/503/504，脚本已内置重试。
- 注销列表不直接提供机构类型，必须进入注销详情页二次确认是否为“私募证券投资基金管理人”。

## 2. V1 报告口径

### 全国证券私募管理人重点变化

默认统计窗口：

- 年初至报告日，例如 `2026-01-01` 至 `2026-05-07`。

新增管理人：

- 筛选条件：`primaryInvestType = 私募证券投资基金管理人`
- 日期字段：`registerDate`
- V1 图片不展开新增明细，只展示总数和简短判断。
- Markdown/JSON 中保留新增明细，便于后续复核。

重点新设线索：

- 从管理人详情页提取管理规模区间、实控人、高管、全职员工人数、基金从业人数、主要出资人、高管任职履历。
- 如出现公募、券商资管、保险资管、信托、银行、头部私募等背景线索，可在文字中点出。
- 仅公开信息整理，不对团队投资能力作判断。

退出/注销管理人：

- 按注销日期筛选后，进入注销详情页确认机构类型。
- 全国退出/注销若规模不大，V1 图片只展示总数。
- 重点退出使用代理指标，不使用“管理规模”表述：
  - 注销时产品数量
  - 注册资本
  - 实缴资本
- 默认阈值：
  - 产品数量 >= 5 只，或
  - 注册资本/实缴资本 >= 5,000 万元

### 陕西证券私募动态

默认统计窗口：

- 年初至报告日。

口径：

- 注册地或办公地在陕西省的证券私募管理人。

栏目：

- 陕西今年以来新增证券私募管理人
- 陕西今年以来退出/注销证券私募管理人

因陕西动态较少，V1 图片保留陕西退出/注销明细；如新增存在，也可保留新增明细。

### 办公地在陕西的私募管理人新产品备案

默认统计窗口：

- 年初至报告日。

匹配方法：

1. 拉取办公地为陕西省的证券私募管理人名单。
2. 拉取统计窗口内备案的私募证券投资基金。
3. 按管理人名称或管理人 ID 匹配陕西办公地管理人。

展示字段：

- 备案产品名称
- 管理人
- 托管人
- 备案日期
- 成立日期
- 基金编号

## 3. 每日生成命令

脚本位置：

`v1/陕西省证券私募日报v1/scripts/amac_security_private_daily.py`

正常运行：

```bash
python3 v1/陕西省证券私募日报v1/scripts/amac_security_private_daily.py \
  --date YYYY-MM-DD \
  --shaanxi-since YYYY-01-01 \
  --max-cancel-pages 80 \
  --max-cancel-details 600 \
  --max-product-pages 220
```

全国板块 KPI 为“报告日当天”口径；脚本会自动追加 `YYYY-01-01` 至报告日的全国累计新增、累计退出/注销和重点样本说明。

示例：

```bash
python3 v1/陕西省证券私募日报v1/scripts/amac_security_private_daily.py \
  --date 2026-05-07 \
  --shaanxi-since 2026-01-01 \
  --max-cancel-pages 80 \
  --max-cancel-details 600 \
  --max-product-pages 220
```

输出文件：

- Markdown：`v1/陕西省证券私募日报v1/outputs/security-private-fund-daily-YYYY-MM-DD.md`
- 原始 JSON：`v1/陕西省证券私募日报v1/data/security-private-fund-daily-YYYY-MM-DD.json`

## 3.1 Token 友好的增量运行建议

当前 V1 的报告口径是“年初至报告日”，每日命令也按年初至报告日拉取协会数据。因此它适合保证统计完整性，但不适合把全量 JSON 或全年明细每天交给大模型复核；截至 2026-05-08，单日原始 JSON 已达到数 MB 级，若直接进入上下文会明显消耗 token。

建议升级为 V1.1 的两层数据结构，并把日常运行拆成“观察环节”和“正式日报环节”：

### 观察环节（默认日常模式）

适用：协会数据低频更新、当天不确定是否有新增时。

目标是用最少上下文判断“是否值得生成日报”，不让模型阅读全年 JSON。

- 只跑最近 3-7 天窗口，生成增量候选摘要。
- 只向模型提供：
  - 当日/近 7 天新增管理人、注销管理人、新备案产品的数量。
  - 陕西注册地或办公地命中的新增、注销、产品备案候选。
  - 与上一期累计摘要的差异。
- 若无新增、无注销、无陕西新备案产品，记录“观察无新增”，不生成新 Markdown、HTML、PNG，不上传 ima。
- 若只有全国新增但无陕西相关或重点退出，可只更新本地事件库，暂不发布日报。
- 若出现陕西相关变化、重点退出/注销、重要机构背景新增或口径差异，再进入正式日报环节。

### 正式日报环节（有增量才触发）

- 从事件库累计生成“年初至报告日”口径的 Markdown/HTML/PNG。
- 只把“本次新增/变更明细 + 累计统计摘要 + 待确认差异”交给模型复核。
- 发布后将本期增量写入事件库，并生成 ima 上传记录。

### 事件库建议

- 首次运行：按 `YYYY-01-01` 至报告日全量抓取，生成基准事件库，例如 `data/security-private-fund-ledger-2026.json`。
- 每日运行：只检索报告日或最近 3-7 天窗口，例如 `--since YYYY-MM-DD --date YYYY-MM-DD`，得到增量候选。
- 合并规则：按管理人登记编号、管理人 ID、基金编号、注销管理人 `userTenantId/orgCode` 去重；新增记录写入事件库，已存在记录只更新状态、日期、详情链接和关键字段。
- 出图/日报：仍从本地事件库汇总“年初至报告日”的累计数，不再每天重新让模型阅读全年明细。
- 兜底校验：每周或每月做一次年初至今全量重跑，与事件库比对差异，修正接口回填、延迟披露或历史数据变更。

推荐日常窗口：

- 协会新增管理人、产品备案：当天或最近 3 天。
- 注销管理人：最近 7 天，因注销详情和列表排序存在延迟风险。
- 陕西专项：最近 7 天，同时保留陕西关键词检索，避免地址字段更新导致漏掉。

执行原则：

- 大模型只阅读“今日新增/变更候选 + 本地累计统计摘要 + 差异清单”。
- 不把 `raw.allSecurityProductsInWindow` 这类全年原始数组直接放入模型上下文。
- 发布口径仍写“年初至报告日”，但计算来源变为“事件库累计 + 今日增量”。

## 4. 图片制作规则

严禁用 AI 图片生成模型直接生成文字图，避免产品名、日期、数字被改写。

必须使用：

- HTML/CSS 文本排版
- Chrome headless 截图导出 PNG
- 人工或程序校验数字

V1 图片结构：

1. 顶部标题、日期、统计窗口
2. 四个 KPI：
   - 全国今年新增证券私募
   - 全国重点退出/注销
   - 陕西今年退出/注销
   - 陕西今年新备案产品
3. 全国证券私募管理人重点变化
4. 陕西证券私募动态
5. 办公地在陕西的管理人新产品备案
6. 底部来源与免责声明

默认文件：

- HTML：`v1/陕西省证券私募日报v1/outputs/security-private-fund-daily-YYYY-MM-DD-publish.html`
- PNG：`v1/陕西省证券私募日报v1/outputs/YYYY年M月D日证券私募行业动态日报.png`

HTML 页脚和最终 PNG 都必须包含来源标识：`华泰证券西安锦业路证券营业部（西北分公司机构业务中心）` 和 `https://refrain97.github.io/shaanxi-capital-market-daily/v1/`。导出 PNG 后执行：

```bash
python3 v1/scripts/brand_v1_png.py "v1/陕西省证券私募日报v1/outputs/YYYY年M月D日证券私募行业动态日报.png"
```

上传 ima 前，`v1/scripts/upload_daily_ima.sh` 也会自动补一次。

导出命令：

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless \
  --disable-gpu \
  --hide-scrollbars \
  --force-device-scale-factor=1 \
  --window-size=1242,1810 \
  --screenshot=/path/to/YYYY年M月D日证券私募行业动态日报.png \
  /path/to/security-private-fund-daily-YYYY-MM-DD-publish.html
```

导出后检查尺寸：

```bash
sips -g pixelWidth -g pixelHeight /path/to/YYYY年M月D日证券私募行业动态日报.png
```

打开预览：

```bash
open /path/to/security-private-fund-daily-YYYY-MM-DD-publish.html
open /path/to/YYYY年M月D日证券私募行业动态日报.png
```

## 5. 发布前校验

必须检查：

- 顶部统计窗口是否为年初至报告日。
- 全国新增证券私募数量是否与 JSON 中 `nationalAdditions` 数量一致。
- 全国退出/注销数量是否与 JSON 中 `nationalCancellationTotal` 一致。
- 陕西退出/注销数量是否与 JSON 中 `shaanxiCancellations` 一致。
- 陕西新备案产品数量是否与 JSON 中 `shaanxiOfficeProducts` 一致。
- 图片中文字无截断、无重叠、底部免责声明完整。
- 产品名称、管理人、托管人、日期、基金编号未被改写。

本次 V1 样例校验：

- 报告日：`2026-05-07`
- 统计窗口：`2026-01-01 至 2026-05-07`
- 全国今年新增证券私募：17 家
- 全国已确认证券私募退出/注销：14 家
- 全国重点退出/注销：8 家
- 陕西今年退出/注销：1 家
- 陕西今年新备案产品：9 只

## 6. ima 入库规则

目标知识库：

`公告检索`

文件名：

`YYYY年M月D日证券私募行业动态日报.png`

上传流程：

1. `preflight-check.cjs` 检查 PNG 类型和大小。
2. `search_knowledge_base` 查找 `公告检索`，取得 `knowledge_base_id`。
3. `check_repeated_names` 检查同名文件。
4. 如已重名，使用 `_v2` 后缀，不替换原文件。
5. `create_media` 创建媒体并取得 COS 凭证。
6. `cos-upload.cjs` 上传 PNG 到 COS。
7. `add_knowledge` 添加入库。
8. `search_knowledge` 用完整文件名和日期关键词检索验证。

本机脚本：

- 类型预检：`~/.workbuddy/skills/腾讯ima/knowledge-base/scripts/preflight-check.cjs`
- COS 上传：`~/.workbuddy/skills/腾讯ima/knowledge-base/scripts/cos-upload.cjs`

上传记录：

`v1/陕西省证券私募日报v1/outputs/ima-upload-security-private-fund-YYYY-MM-DD.json`

本次 V1 样例：

- 知识库：`公告检索`
- 文件名：`2026年5月7日证券私募行业动态日报.png`
- 完整文件名检索：命中
- 日期关键词检索：命中

## 7. 归档文件清单

每日建议保留：

- Markdown 底稿
- 原始 JSON
- 可编辑 HTML
- 发布 PNG
- ima 上传记录 JSON

V1 示例文件：

- `v1/陕西省证券私募日报v1/outputs/security-private-fund-daily-2026-05-07.md`
- `v1/陕西省证券私募日报v1/data/security-private-fund-daily-2026-05-07.json`
- `v1/陕西省证券私募日报v1/outputs/security-private-fund-daily-2026-05-07-publish.html`
- `v1/陕西省证券私募日报v1/outputs/2026年5月7日证券私募行业动态日报.png`
- `v1/陕西省证券私募日报v1/outputs/ima-upload-security-private-fund-2026-05-07.json`

## 8. 后续迭代方向

V2 可考虑：

- 增加重点新设管理人的外部履历核验，如官网、新闻、工商信息。
- 将全国新增管理人按地区、登记日期、规模区间做小图表。
- 对陕西产品备案按管理人维度聚合，展示今年以来发行活跃度。
- 增加异常提示：若协会接口返回异常或数量显著偏离历史区间，自动标注“需复核”。
