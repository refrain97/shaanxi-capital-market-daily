# V3 统一数据契约

版本：0.6  
生效日期：2026-07-12  
状态：实现前必须遵守的主数据规范

## 1. 设计目标

V3 以主数据驱动页面、推送和年度统计。数据模型必须解决五件事：

1. 同一主体换称呼后仍能识别。
2. 同一事件跨日期、跨来源、跨频道只保留一份主记录。
3. 客观事实、编辑判断和业务动作相互分离。
4. 公告时间、发现时间、截止时间和结果时间不混用。
5. 日内快照和年度累计从同一底座计算。

## 2. 核心对象

V3 使用十一个核心对象：

| 对象 | 含义 | 是否年度累计 |
|---|---|---|
| `entity` | 公司、集团、人员、基金、项目等主体 | 是 |
| `sourceRecord` | 某一来源抓到的原始记录 | 是 |
| `evidence` | 支撑事实的正文、附件和关键字段 | 是 |
| `event` | 去重后的客观事项 | 是 |
| `signal` | 对事件的重要性和业务意义判断 | 是 |
| `lead` | 可执行的业务线索和下一步动作 | 是 |
| `watchItem` | 用户对唯一事件的收藏、备注和复核状态 | 否，单独保留历史 |
| `listedDaily` | 一次上市公司完整检索及有效事项归并结果 | 否，按报告日保存 |
| `financialReport` | 年报、季报、预告、快报、问询和分红结构化记录 | 是 |
| `tenderMonitor` | 招投标来源、扫描、机会、候选、排除和漏检状态 | 否，运行日志另存 |
| `snapshot` | 某次上午或盘后更新的对象引用 | 否 |

`event` 是年度统计的主计数单位，`snapshot` 不能用于累计事件数。

## 3. Entity 主体

### 3.1 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `entityId` | string | 稳定唯一 ID |
| `entityType` | enum | `listed_company`、`soe_group`、`private_manager`、`fund`、`person`、`tender_project`、`financing_company` 等 |
| `canonicalName` | string | 对外标准名称 |
| `aliases` | string[] | 简称、证券简称、历史名称、常用名 |
| `region` | string | 地区 |
| `status` | enum | `active`、`inactive`、`cancelled`、`unknown` |
| `firstSeenAt` | datetime | 首次进入主体库时间 |
| `lastSeenAt` | datetime | 最近被来源确认时间 |

上市公司主体还应保存：

- `universeTier`：`L1` 陕西辖区 A 股、`L2` 陕西港股、`L3` 陕西关联上市公司。
- `inclusionReason`、`sourceAsOf`、`sourceFile` 和 `sourceRow`。
- `securityListings`：同一主体的 A 股、H 股或其他上市代码数组。
- `excluded` 和 `excludedReason`：保留显式排除审计。

### 3.2 可选识别字段

- 证券代码、统一社会信用代码、AMAC 登记编号、基金编号。
- 招标项目编号、辅导备案编号、公告机构内部 ID。
- `parentEntityId`、`relatedEntityIds` 和关系类型。

### 3.3 主体规则

- 主题词、产品词、事项词不能作为公司实体。
- 股东、子公司与上市公司分别建实体，再用关系连接。
- 证券简称变化时保留原 `entityId`，只更新别名和时间线。
- A+H 公司保持一个 `entityId`，不得因市场代码不同重复建主体。
- 无法稳定识别时使用待核验临时 ID，核验后必须归并。

## 4. SourceRecord 来源记录

每次采集命中的原始记录都保存为 `sourceRecord`，不得先改写成结论再落盘。

| 字段 | 必填 | 说明 |
|---|---|---|
| `sourceRecordId` | 是 | 唯一 ID |
| `sourceRunId` | 是 | 本次来源采集运行 ID |
| `providerId` | 否 | 使用数据服务商时填写配置中的 Provider ID |
| `sourceType` | 是 | 官方公告、监管、协会、企业官网、平台、媒体、聚合页、搜索摘要 |
| `sourceName` | 是 | 来源名称 |
| `url` | 是 | 原始链接或稳定附件引用 |
| `title` | 是 | 原始标题 |
| `publishedAt` | 否 | 来源发布时间，未知为 null |
| `fetchedAt` | 是 | 抓取时间 |
| `contentHash` | 是 | 内容去重哈希 |
| `rawPath` | 否 | 本地原文或附件引用 |
| `httpStatus` | 否 | 抓取状态 |
| `sourceQuality` | 是 | `official`、`authoritative`、`secondary`、`discovery_only` |

搜索摘要和聚合页默认是 `discovery_only`，只能产生候选。

### 4.1 ProviderRun 数据服务体检

每个上午或盘后班次，对计划使用的金融数据 Provider 保存一条体检记录：

| 字段 | 必填 | 说明 |
|---|---|---|
| `providerId` | 是 | `config/data-providers.json` 中的稳定 ID |
| `skillRootId` | 是 | 非敏感路径标识，不保存密钥路径 |
| `status` | 是 | `PASS`、`DEGRADED`、`FAIL_AUTH`、`FAIL_NETWORK`、`FAIL_QUOTA`、`FAIL_SCHEMA` |
| `checkedAt` | 是 | 本班次真实探针时间 |
| `latencyMs` | 否 | 探针耗时 |
| `errorCode` | 否 | 脱敏错误码，不保存完整鉴权响应 |
| `dataAsOf` | 否 | 数据服务返回的数据时点 |
| `affectedChannels` | 是 | 失败或降级影响的频道 |

Provider 体检记录严禁包含密钥、Token、Cookie、Authorization Header 或完整调用命令。

## 5. Evidence 证据

| 字段 | 必填 | 说明 |
|---|---|---|
| `evidenceId` | 是 | 唯一 ID |
| `sourceRecordId` | 是 | 对应原始记录 |
| `evidenceType` | 是 | PDF、网页正文、表格、接口字段、OCR、交叉来源 |
| `factPath` | 是 | 支撑哪个事实字段 |
| `excerpt` | 否 | 合规长度的关键摘录或摘要 |
| `value` | 否 | 结构化值 |
| `unit` | 否 | 元、股、%、人、只、家等 |
| `verifiedAt` | 否 | 核验时间 |
| `verificationStatus` | 是 | `verified`、`cross_checked`、`pending`、`conflict` |

关键数字必须能从事件字段追溯到对应 `evidenceId`。

## 6. Event 事件

### 6.1 核心字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `eventId` | 是 | 年度内稳定唯一 ID |
| `eventKey` | 是 | 规范化去重键 |
| `channel` | 是 | 六个频道之一 |
| `eventType` | 是 | 频道定义的事件类型 |
| `primaryEntityId` | 是 | 主体 |
| `relatedEntityIds` | 否 | 股东、子公司、人员、对手方等 |
| `title` | 是 | 事实型短标题 |
| `summary` | 是 | 客观摘要，不含业务建议 |
| `occurredAt` | 否 | 事项实际发生时间 |
| `publishedAt` | 否 | 首次公开发布时间 |
| `discoveredAt` | 是 | V3 首次发现时间 |
| `deadlineAt` | 否 | 行动截止时间 |
| `resultAt` | 否 | 结果发布时间 |
| `lastCheckedAt` | 是 | 最近核验时间 |
| `eventStatus` | 是 | 当前事件状态 |
| `noveltyStatus` | 是 | `new`、`progress`、`backfill`、`unchanged` |
| `qualityStatus` | 是 | `verified`、`cross_checked`、`pending`、`conflict` |
| `sourceRecordIds` | 是 | 支撑来源列表 |
| `evidenceIds` | 否 | 关键证据列表 |
| `metrics` | 否 | 结构化关键数字 |
| `timeline` | 是 | 状态变化节点 |

### 6.2 Event 状态

通用状态：

`candidate -> verified -> active -> progressing -> completed / terminated -> archived`

可根据频道使用更细状态，但不得跳过候选与核验逻辑。`backfill` 是新颖性状态，不是把历史事项重新变成活跃机会。

### 6.3 EventKey

事件键优先使用官方稳定标识：公告 ID、基金编号、招标编号、交易方案编号等。没有稳定标识时按以下组合生成：

```text
primaryEntityId + eventType + normalizedObject + firstPublishedDate
```

同一事件的新公告、问询、回复、候选、结果和终止写入 `timeline`，不创建新的主事件。

## 7. Signal 信号

`signal` 是编辑和业务判断层，不得修改事件事实。

| 字段 | 必填 | 说明 |
|---|---|---|
| `signalId` | 是 | 唯一 ID |
| `eventId` | 是 | 关联唯一事件 |
| `headline` | 是 | 面向观众的短标题 |
| `whyItMatters` | 是 | 为什么值得关注 |
| `primaryBusiness` | 是 | 主业务 |
| `secondaryBusinesses` | 否 | 辅助业务 |
| `priority` | 是 | `high`、`medium`、`low` |
| `score` | 否 | 统一评分 |
| `signalStatus` | 是 | `today_new`、`action_window`、`risk`、`data_update`、`result_progress`、`backfill`、`watch`、`miss_review` |
| `actionable` | 是 | 是否可行动 |
| `reasoning` | 是 | 判断依据，必须与事件事实区分 |
| `createdAt` | 是 | 创建时间 |
| `updatedAt` | 是 | 更新时间 |

一个 `eventId` 同一时点只能有一个主 `signalId`。页面间复用信号引用，不复制文本生成新信号。

## 8. Lead 业务线索

| 字段 | 必填 | 说明 |
|---|---|---|
| `leadId` | 是 | 唯一 ID |
| `signalId` | 是 | 关联信号 |
| `targetEntityId` | 是 | 建议跟进对象 |
| `businessType` | 是 | 业务方向 |
| `opportunityType` | 是 | 承销、财顾、托管、机构服务、客户维护等 |
| `rationale` | 是 | 公开事实下的业务依据 |
| `nextAction` | 是 | 下一步动作 |
| `dueAt` | 否 | 动作截止或复核时间 |
| `leadStatus` | 是 | `to_assess`、`to_contact`、`following`、`waiting`、`converted`、`closed` |
| `confidence` | 是 | `high`、`medium`、`low` |
| `owner` | 否 | 内部负责人；公开页面不得展示非公开信息 |

线索是建议，不得在没有事实依据时写成已联系、已承揽或已成交。

## 9. Snapshot 更新快照

| 字段 | 必填 | 说明 |
|---|---|---|
| `snapshotId` | 是 | `YYYY-MM-DD-morning/closing` |
| `runId` | 是 | 对应运行记录 |
| `date` | 是 | 报告日期 |
| `slot` | 是 | `morning` 或 `closing` |
| `generatedAt` | 是 | 生成时间 |
| `dataCutoffAt` | 是 | 数据截止时间 |
| `previousSnapshotId` | 否 | 上一成功快照 |
| `newEventIds` | 是 | 本次新事件 |
| `updatedEventIds` | 是 | 本次进展事件 |
| `activeSignalIds` | 是 | 本次展示信号 |
| `leadIds` | 是 | 本次业务线索 |
| `sourceHealth` | 是 | 各来源及 Provider 的本班次健康状态、数据时点和影响范围 |
| `qualityResult` | 是 | 质量闸门结果 |

快照保存引用和差异，不重复保存全年事件正文。

## 10. WatchItem 长期跟踪

`watchItem` 只保存用户工作状态，并始终引用唯一 `eventId`；不得复制或改写事件事实。

| 字段 | 必填 | 说明 |
|---|---|---|
| `watchId` | 是 | 稳定唯一 ID |
| `eventId` | 是 | 被跟踪的唯一事件 |
| `entityId` | 是 | 必须与事件主主体一致 |
| `watchStatus` | 是 | `saved`、`to_review`、`following`、`waiting`、`resolved`、`closed` |
| `priority` | 是 | `high`、`medium`、`low` |
| `tags` | 是 | 用户标签数组，同一项内不得重复 |
| `business` | 否 | 公开业务方向，不代替事件频道 |
| `note` | 是 | 用户工作备注，不进入事件摘要和证据 |
| `nextReviewAt` | 条件必填 | 活动状态必须填写；结束状态可为 null |
| `createdAt` | 是 | 首次收藏时间 |
| `updatedAt` | 是 | 最近修改时间，不得早于 `createdAt` |
| `stateHistory` | 是 | 状态、时间历史；末项必须等于当前状态 |

同一事件最多存在一个跟踪项。取消跟踪只删除本机工作项，不删除事件；需要保留工作历史时，应将状态改为 `closed`。

## 11. ListedDaily 上市公司完整日报

`listedDaily` 保存一次逐公司检索的覆盖和归并结果，不复制事件正文。原始公告是披露计数单位，`eventId` 是有效事项和年度统计单位。

| 字段 | 必填 | 说明 |
|---|---|---|
| `reportDate`、`windowStart`、`windowEnd` | 是 | 报告日与实际检索窗口 |
| `universeCount` | 是 | 本次逐公司检索主体数 |
| `announcementCount` | 是 | 命中的唯一原始公告数 |
| `coveredCompanyCount` | 是 | 发布公告的唯一主体数 |
| `effectiveEventCount` | 是 | 去重归并后的有效事项数 |
| `retrievalErrorCount` | 是 | 逐公司检索错误数 |
| `queryMethod`、`sourceStatus` | 是 | 检索方法和来源状态 |
| `items` | 是 | 有效事项引用数组 |

每个 `item` 必须引用一个上市公司 `eventId`、匹配的 `entityId` 和全部 `sourceRecordIds`，并保存 RM 分类、重要性与纳入原因。同一公告只能属于一个本期事项；中介核查、会计师说明、董事会决议和会议资料若属于同一事项，归并到同一事件但保留全部来源链接。

## 12. FinancialReport 财务披露

| 字段 | 必填 | 说明 |
|---|---|---|
| `financialReportId`、`eventId`、`entityId` | 是 | 唯一记录及事件、主体引用 |
| `period`、`disclosureType`、`currency` | 是 | 报告期、披露类型和原币种 |
| `revenue`、`revenueYoY` | 是，可为 null | 营业收入和同比 |
| `netProfitLower/Upper`、同比区间 | 是，可为 null | 归母净利润及同比；单值上下界相同 |
| `adjustedNetProfitLower/Upper`、同比区间 | 是，可为 null | 扣非净利润及同比 |
| `operatingCashFlow`、`grossMargin`、`netMargin` | 是，可为 null | 现金流与利润率 |
| `dividendPerShare`、`dividendTotal` | 是，可为 null | 每股分红和分红总额 |
| `businessMix`、`anomalies` | 是 | 业务结构变化和异常项 |
| `auditStatus`、`sourceRecordIds` | 是 | 审计/问询状态和原始来源 |

未披露值必须为 `null`，不得根据同比或区间反推补写。不同币种、不同报告期和预告/正式报告不得直接求和；比较页面必须显示报告期、币种和披露类型。

## 13. TenderMonitor 招投标即时发现

`tenderMonitor` 由来源注册、扫描运行、项目状态和发现记录组成。网页上午/盘后快照不改变采集层30至60分钟的目标频率。

| 对象/字段 | 说明 |
|---|---|
| `scanIntervalMinutes` | 30至60分钟；原型固定60分钟 |
| `schedulerEnabled`、`schedulerStatus` | 必须真实反映自动调度状态 |
| `activeOpportunityEventIds` | 仅引用公告期、截止有效、资格适配且已回源的招投标事件 |
| `projects` | 已建立唯一项目的状态、资格、截止、首次发现阶段和漏检记录 |
| `findings` | 尚未升级为事件的搜索候选、结果线索和排除记录 |
| `scanRuns` | 开始、结束、来源范围、候选、机会、结果、排除和运行状态 |

机会分类结果固定为：`active_opportunity`、`pending`、`history`、`excluded`。搜索摘要只能进入 `pending`；候选、中标、成交、首次发现已截止统一进入 `history/miss_review`，不得进入机会区。

来源注册表独立保存在 `config/tender-sources.json`，记录权威级别、页面入口、公告阶段、扫描频率和组合检索词。注册不等于适配器已运行，`schedulerEnabled=false` 时页面必须明确显示“调度待启用”。

## 14. PrivateFundSnapshot 证券私募快照

私募数据独立保存为按日快照，并由网页读取 `data/private-fund/snapshots/latest.json`。

| 对象/字段 | 说明 |
|---|---|
| `topManagers` | 前20管理人、登记编号、可复算活跃分、员工和高管详情 |
| `newProducts` | 与上一V1快照按 `fundNo` 比较得到的新增备案 |
| `personnelChanges` | 仅在存在上一V3详情快照时生成的高管和员工字段变化 |
| `custodianSummary` | 年内备案产品AMAC托管人字段汇总，不代表全部合作 |
| `locationObservations` | 注册地与办公地异省观察，不等于迁入迁出 |
| `businessTaxonomy` | RM Dashboard私募PB六类业务映射 |

活跃分只表示公开信息活跃度。首期详情快照必须为 `baseline_created` 且人员变化为空；疑似重新活跃和地址迁移必须保留候选状态。

## 15. 业务分类

主业务枚举建议：

- `investment_banking`：投行与上市服务。
- `bond_financing`：债券承销、受托管理、ABS/REITs。
- `ma_advisory`：并购重组和财务顾问。
- `equity_financing`：股权融资、产业基金、Pre-IPO。
- `private_fund_service`：私募机构、产品、托管和运营服务。
- `wealth_institutional`：财富与机构销售。
- `research_service`：研究、投研和风险服务。
- `client_coverage`：主体维护和综合客户服务。

上市公司公告可同时保留 RM Dashboard 一级标签：资本运作、股东服务、激励与员工、资金与财务、治理关系、风险沟通、业绩与分红、经营与产业。

每个上市公司日报事项还必须保存：

- `rmSubcategory`：来自 `config/listed-business-taxonomy.json` 的二级业务标签。
- `businessPriority`：`focus` 或 `standard`，严格由二级标签配置决定。
- `targetObjects`：该一级业务对应的主要跟进对象。
- `importance`：内容重要性，和业务重点分开判断。

`股份回购`属于“资本运作”重点标签；`回购注销`属于“激励与员工”重点标签。出现限制性股票或激励股份回购注销时，不得归入股份回购。

## 16. 年度派生指标

年度指标只能从 `entity`、`event`、`signal` 和 `lead` 查询计算：

- 唯一事件数：去重 `eventId`。
- 活跃主体数：去重 `primaryEntityId`。
- 本月新增：`discoveredAt` 在本月且 `noveltyStatus=new`。
- 进展数：既有事件新增时间线节点。
- 行动窗口：`actionable=true` 且截止和状态校验通过。
- 漏检数：`signalStatus=miss_review`。
- 线索转化：仅统计有状态记录的 `leadId`，不从文案推断。

所有 KPI 必须能够下钻到组成对象 ID。

## 17. 建议目录结构

```text
v3/
  data/
    master/entities.json
    master/aliases.json
    raw/YYYY-MM-DD/{source}/
    events/YYYY/events.jsonl
    signals/YYYY/signals.jsonl
    leads/YYYY/leads.jsonl
    watches/watch-items.jsonl
    listed-daily/YYYY-MM-DD.json
    financial-reports/YYYY/reports.jsonl
    private-fund/snapshots/YYYY-MM-DD.json
    tender/runs/YYYY-MM-DD/*.json
    tender/projects/YYYY/projects.jsonl
    snapshots/YYYY-MM-DD/{morning|closing}.json
    runs/YYYY-MM-DD/{runId}.json
  schemas/
  validators/
  site/
```

原始 PDF 和 V1 历史长图不复制进 V3；使用稳定路径或证据索引引用。

## 18. 最小事件示例

```json
{
  "eventId": "evt-listed-2026-001286-1225417856",
  "eventKey": "cninfo:1225417856",
  "channel": "listed_company",
  "eventType": "shareholder_reduction_plan",
  "primaryEntityId": "listed:001286",
  "relatedEntityIds": ["company:changan-huitong"],
  "title": "陕西能源股东披露减持计划",
  "publishedAt": "2026-07-10T00:00:00+08:00",
  "discoveredAt": "2026-07-10T08:20:00+08:00",
  "deadlineAt": "2026-10-29T23:59:59+08:00",
  "eventStatus": "active",
  "noveltyStatus": "new",
  "qualityStatus": "verified",
  "sourceRecordIds": ["src-cninfo-1225417856"],
  "evidenceIds": ["evd-cninfo-1225417856-reduction-limit"],
  "timeline": []
}
```
