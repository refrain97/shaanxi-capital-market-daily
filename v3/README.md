# 陕西资本市场情报 V3

V3 是一套日频两次更新的陕西资本市场机构情报系统。V1 继续承担稳定的数据日档和历史发布，V3 在独立目录内建立统一实体、事件、信号、线索和年度统计，不直接改写 V1 生产流程。

当前状态：`并行原型 0.9`。Phase 1 至 Phase 6 蓝图均已实现：统一关系层266个节点/128条证据边、分口径年度总览和三次日更运行入口已落地。自动化 `v3` 每日03:30全量运行，`v3-2` 每日12:00午间更新，`v3-17` 每日17:00更新；招投标随三次统一流程刷新。当前部分频道仍可能出现旧输入，因此运行结果会诚实标为 `PASS_WITH_STALE_INPUT`，尚不宣称正式生产发布。

## 上下文恢复顺序

任何新任务、上下文压缩后的续作或新代理接手，都必须按以下顺序读取，不依赖聊天记忆：

1. 本文件，确认项目边界、当前状态和文档权威级别。
2. `docs/00-V3-MASTER-SOP.md`，恢复完整生产逻辑。
3. `docs/04-V3-QUALITY-GATES.md`，确认不得违反的强约束。
4. `docs/08-V3-DATA-PROVIDERS.md` 和 `config/data-providers.json`，确认实际调用路径、探针和降级规则。
5. `docs/02-V3-DATA-CONTRACT.md`，确认数据对象、时间和去重口径。
6. `docs/03-V3-CHANNEL-SOPS.md`，确认各频道输入、输出和特有规则。
7. `docs/07-V3-LISTED-UNIVERSE.md`，确认上市公司主体池、关联线索和排除名单。
8. `docs/05-V3-DAILY-RUNBOOK.md`，确认上午版、盘后版的执行顺序。
9. `docs/01-V3-PRESENTATION-SPEC.md`，确认页面和年度统计表现形式。
10. `docs/09-V3-PRODUCT-BLUEPRINT.md`，确认频道深化、收藏跟踪和下一阶段实施顺序。
11. `docs/10-V3-PRIVATE-FUND-SOP.md`，确认私募排名、人员差异和关系边界。
12. `docs/11-V3-MA-PREIPO-SOP.md`，确认并购项目、上市后备和融资证据边界。
13. `docs/12-V3-RELATION-PRODUCTION-SOP.md`，确认关系、年度口径、日更运行和STALE规则。
14. `docs/06-V3-DECISION-LOG.md`，确认用户已定方向和后续变更。
15. `docs/13-V3-EVENT-STORE-SOP.md`，确认事件去重、版本和原始快照规则。
16. `docs/build-roadmap.md`，确认实现阶段和完成状态。

发生规则冲突时，优先级为：`质量强约束 > 数据源 SOP > 数据契约 > 上市公司主体池 > 总 SOP > 频道 SOP > 运行手册 > 产品蓝图 > 表现规范 > 路线图 > 历史愿景文档`。

## 文档目录

| 文件 | 作用 | 权威级别 |
|---|---|---|
| `docs/00-V3-MASTER-SOP.md` | 从采集到发布、复盘的总流程 | 核心 |
| `docs/01-V3-PRESENTATION-SPEC.md` | 业务看板、年度数据和页面验收标准 | 核心 |
| `docs/02-V3-DATA-CONTRACT.md` | 实体、事件、信号、线索、跟踪和快照数据契约 | 核心 |
| `docs/03-V3-CHANNEL-SOPS.md` | 六个频道的输入、判断和输出规范 | 核心 |
| `docs/04-V3-QUALITY-GATES.md` | 阻断发布的强约束和验证规则 | 最高 |
| `docs/05-V3-DAILY-RUNBOOK.md` | 上午、盘后更新及异常处理清单 | 核心 |
| `docs/06-V3-DECISION-LOG.md` | 已确认需求、设计偏好和决策变更 | 记录 |
| `docs/07-V3-LISTED-UNIVERSE.md` | A股、港股和陕西关联上市公司主体池口径 | 核心 |
| `docs/08-V3-DATA-PROVIDERS.md` | Wind、iFinD、官方源的调用、探针、冲突与降级规则 | 核心 |
| `docs/09-V3-PRODUCT-BLUEPRINT.md` | 上市公司、私募、并购、拟上市融资、招投标和长期跟踪蓝图 | 核心 |
| `docs/10-V3-PRIVATE-FUND-SOP.md` | 私募管理人、人员、产品、关系和异动规则 | 核心 |
| `docs/11-V3-MA-PREIPO-SOP.md` | 并购项目、上市后备企业和融资证据规则 | 核心 |
| `docs/12-V3-RELATION-PRODUCTION-SOP.md` | 关系层、年度分析、两次日更和并行试运行规则 | 核心 |
| `docs/13-V3-EVENT-STORE-SOP.md` | 统一事件键、版本历史、时间线和原始快照规则 | 核心 |
| `config/data-providers.json` | 不含密钥的 Provider 路径、职责和探针配置 | 配置 |
| `config/listed-business-taxonomy.json` | 上市公司八个一级业务、43个二级标签、21个业务重点及跟进对象 | 配置 |
| `data/listed/universe.json` | 上市公司完整跟踪池：L1 85、L2 14、L3 18，共117家 | 主数据 |
| `schemas/dashboard-data.schema.json` | 本地原型统一对象、上市日报、财务披露、招投标监控和快照 Schema 0.5 | 实现 |
| `schemas/private-fund-snapshot.schema.json` | 私募管理人、人员、产品和关系快照 Schema 0.1 | 实现 |
| `data/sample/dashboard-2026-07-10.json` | 从 V1 真实公开资料规范化的六频道样例 | 数据 |
| `scripts/validate_data.mjs` | 样例唯一性、引用、时间、行动和 Provider 核心校验 | 实现 |
| `scripts/validate_listed_business_taxonomy.mjs` | 校验上市公司业务分类、重点集合及回购分类边界 | 实现 |
| `scripts/build_listed_universe.py` | 从V1陕西A股池、港股核验和关联线索生成117家主体池 | 实现 |
| `scripts/validate_listed_universe.mjs` | 校验L1/L2/L3总数、去重、排除和抓取覆盖边界 | 实现 |
| `scripts/upgrade_phase2_data.mjs` | 从 V1 真实公告资产可重复生成 Phase 2 上市公司样例 | 实现 |
| `config/tender-sources.json` | 招投标官方来源、60分钟目标和组合检索词注册表 | 配置 |
| `scripts/classify_tender.mjs` | 公告期、截止、资格与来源质量分类器 | 实现 |
| `scripts/validate_tender_classifier.mjs` | 招投标机会准入与漏检分流测试 | 实现 |
| `scripts/upgrade_phase3_data.mjs` | 从 V1 观察结果生成招投标监控原型 | 实现 |
| `scripts/scan_tender_sources.mjs` | 真实运行官方全文检索、来源探针、指纹差异、分类和提醒输出 | 实现 |
| `scripts/validate_tender_runtime.mjs` | 校验实时扫描来源、记录、统计、机会准入和差异引用 | 实现 |
| `scripts/build_private_fund_snapshot.py` | 从V1前后快照生成私募前20、人员、产品和公开关系 | 实现 |
| `scripts/validate_private_fund.mjs` | 校验排名、人员基线、新备案和地址观察边界 | 实现 |
| `scripts/build_phase5_data.py` | 将V1并购案例、2026后备名录和核验融资生成项目库 | 实现 |
| `scripts/validate_phase5.mjs` | 校验并购状态、来源覆盖、A档名录、融资证据和上市毕业状态 | 实现 |
| `schemas/ma-projects.schema.json` | 并购项目与里程碑 Schema 0.1 | 实现 |
| `schemas/pre-ipo.schema.json` | 上市后备企业、成长里程碑和融资 Schema 0.1 | 实现 |
| `scripts/build_phase6_data.py` | 生成统一关系层和分口径年度指标 | 实现 |
| `scripts/validate_phase6.mjs` | 校验关系引用、证据和年度口径 | 实现 |
| `scripts/run_v3.py` | 上午/盘后统一运行、质量门和STALE输入记录 | 实现 |
| `scripts/build_event_store.py` | 将五类频道输入归并到统一 SQLite 事件库 | 实现 |
| `scripts/validate_event_store.py` | 校验事件唯一性、版本、外键和频道覆盖 | 实现 |
| `data/runs/latest-morning.json` | 最近一次上午运行结果 | 运行数据 |
| `data/runs/latest-closing.json` | 最近一次盘后运行结果 | 运行数据 |
| `data/private-fund/snapshots/latest.json` | 最近一次证券私募详情快照 | 运行数据 |
| `data/tender/scans/latest.json` | 最近一次真实扫描结果，网页直接读取 | 运行数据 |
| `data/tender/alerts/latest.json` | 本次仍有效机会的即时提醒列表 | 运行数据 |
| `scripts/serve_local.sh` | 从项目根目录启动本地静态服务 | 实现 |
| `site/index.html` | V3 本地业务看板入口 | 实现 |
| `docs/product-vision.md` | 初始产品愿景，作为背景材料保留 | 参考 |
| `docs/build-roadmap.md` | 数据优先的实现计划 | 计划 |

## 产品边界

- V1：稳定生产、历史日档、IMA 和现有网页发布。
- V2：历史试验，不作为 V3 的直接运行依赖。
- `v2-hourly-dashboard`：属于其他 Investment OS 展示包，不计入本项目版本谱系。
- V3：使用只读适配器继承可用数据与约束，建立自己的主数据和网页。

## 本地运行

从项目根目录执行：

```bash
./v3/scripts/serve_local.sh
```

浏览器打开：`http://127.0.0.1:4173/v3/site/`

GitHub Pages 正式预览：`https://refrain97.github.io/shaanxi-capital-market-daily/v3/`

更换端口：

```bash
./v3/scripts/serve_local.sh 4174
```

运行前校验真实样例：

```bash
node v3/scripts/validate_data.mjs
node v3/scripts/validate_private_fund.mjs
node v3/scripts/validate_tender_runtime.mjs
node v3/scripts/validate_phase5.mjs
node v3/scripts/validate_phase6.mjs
```

网页必须通过 HTTP 服务打开；直接双击 HTML 时，浏览器会阻止读取 JSON 数据。

“我的跟踪”在当前本地原型中使用浏览器 `localStorage` 持久化。它适合单机验证收藏、备注、状态和复核流程，不等同于多设备同步或生产数据库。

发布 V3 独立网页：

```bash
./v3/scripts/publish_v3_to_github_pages.sh
```

该脚本只替换 GitHub Pages 的 `/v3/` 子目录，不覆盖现有 V1、V2 或陕西国企动态雷达页面。

## 修改纪律

- 用户确认的新规则不能只留在聊天中；必须同步更新本目录相应 SOP，并在决策日志登记。
- 强约束变更必须同时修改 `04-V3-QUALITY-GATES.md` 和未来验证器测试。
- 数据字段变更必须先修改 `02-V3-DATA-CONTRACT.md`，再修改采集、渲染和页面。
- 上市公司纳入、排除和阈值变更必须更新 `07-V3-LISTED-UNIVERSE.md` 和决策日志。
- 数据服务商、调用路径、探针或降级规则变更必须同步更新 `08-V3-DATA-PROVIDERS.md`、`config/data-providers.json` 和决策日志。
- 频道深化、收藏跟踪或实施顺序变化必须同步更新 `09-V3-PRODUCT-BLUEPRINT.md` 和决策日志。
- 密钥、Token、Cookie 和鉴权响应不得进入 V3 文件、日志或页面。
- 不复制 V1 的大体量历史数据到 V3；V3 只保存规范化事件、快照、索引和必要证据引用。
