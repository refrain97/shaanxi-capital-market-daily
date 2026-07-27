import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { taxonomyTag } from "./listed_business_taxonomy.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const samplePath = path.join(root, "v3/data/sample/dashboard-2026-07-10.json");
const rawPath = path.join(root, "v1/陕西省上市公司日报v1/data/cninfo-shaanxi-announcements-2026-07-10.json");
const universePath = path.join(root, "v3/data/listed/universe.json");
const data = JSON.parse(fs.readFileSync(samplePath, "utf8"));
const raw = JSON.parse(fs.readFileSync(rawPath, "utf8"));
const universe = JSON.parse(fs.readFileSync(universePath, "utf8"));
const announcements = raw["2026-07-09~2026-07-10"];

const upsert = (items, key, value) => {
  const index = items.findIndex((item) => item[key] === value[key]);
  if (index >= 0) items[index] = value;
  else items.push(value);
};

const entities = [
  ["ent-panlong", "盘龙药业", ["陕西盘龙药业集团股份有限公司"], "002864.SZ"],
  ["ent-kanghui", "康惠股份", ["陕西康惠制药股份有限公司"], "603139.SH"],
  ["ent-shaanxi-construction", "陕建股份", ["陕西建工", "陕西建工集团股份有限公司"], "600248.SH"]
].map(([entityId, canonicalName, aliases, securityCode]) => ({
  entityId, entityType: "listed_company", canonicalName, aliases, region: "陕西", status: "active", universeTier: "L1", securityCode
}));
entities.forEach((entity) => upsert(data.entities, "entityId", entity));

const sourceIdByAnnouncement = {
  "1225416899": "src-machinery-pay",
  "1225416889": "src-machinery-meeting",
  "1225416888": "src-machinery-board",
  "1225417168": "src-bank-litigation",
  "1225417165": "src-bank-director",
  "1225417625": "src-panlong-catalogue",
  "1225417856": "src-energy-reduction",
  "1225416877": "src-meichang-forecast",
  "1225414809": "src-aikosai-sponsor",
  "1225414807": "src-aikosai-control",
  "1225414804": "src-aikosai-inquiry",
  "1225414795": "src-aikosai-accountant",
  "1225414634": "src-kanghui-meeting",
  "1225414704": "src-rainbow-forecast",
  "1225415542": "src-shaanxi-construction-dividend"
};

for (const announcement of announcements) {
  const sourceRecordId = sourceIdByAnnouncement[announcement.announcementId];
  const urlDate = announcement.adjunctUrl.match(/finalpage\/(\d{4}-\d{2}-\d{2})/)?.[1] || "2026-07-10";
  upsert(data.sources, "sourceRecordId", {
    sourceRecordId,
    sourceType: "official_announcement",
    sourceName: "巨潮资讯",
    url: `https://static.cninfo.com.cn/${announcement.adjunctUrl}`,
    title: announcement.announcementTitle,
    publishedAt: `${urlDate}T00:00:00+08:00`,
    fetchedAt: "2026-07-10T08:20:00+08:00",
    sourceQuality: "official",
    announcementId: announcement.announcementId,
    securityCode: announcement.secCode
  });
}

const eventRows = [
  {
    eventId: "evt-20260710-bank-director", eventKey: "600928-director-1225417165", eventType: "director_approval",
    primaryEntityId: "ent-xian-bank", title: "西安银行董事侯博任职资格获监管核准",
    summary: "陕西金融监管局核准侯博董事任职资格，属于公司治理层履职进展。",
    sourceRecordIds: ["src-bank-director"], evidenceId: "evd-bank-director", factPath: "governance.directorApproval",
    evidenceValue: "陕金监复〔2026〕121号核准侯博董事任职资格", business: "client_coverage",
    eventStatus: "progressing", signalStatus: "today_new", priority: "medium", rmCategory: "治理关系",
    headline: "西安银行董事任职资格获批", why: "治理层任职正式生效，适合纳入公司治理时间线。",
    reasoning: "监管批复明确，事项已完成。", metric: { label: "监管批复", value: "陕金监复〔2026〕121号" }
  },
  {
    eventId: "evt-20260710-panlong-catalogue", eventKey: "002864-product-1225417625", eventType: "product_catalogue",
    primaryEntityId: "ent-panlong", title: "盘龙药业两项产品进入国家基本药物目录",
    summary: "盘龙七片、通关藤片进入新版国家基本药物目录，后续观察临床使用与渠道放量。",
    sourceRecordIds: ["src-panlong-catalogue"], evidenceId: "evd-panlong", factPath: "operations.productCatalogue",
    evidenceValue: "盘龙七片、通关藤片列入新版国家基本药物目录", business: "research_service",
    eventStatus: "watch", signalStatus: "today_new", priority: "medium", rmCategory: "经营与产业",
    headline: "盘龙药业核心产品进入基药目录", why: "目录准入可能改变医院端和基层渠道覆盖，需等待销售兑现。",
    reasoning: "官方公告确认目录准入，但尚不能直接推导业绩贡献。", metric: { label: "入选产品", value: "2项" }
  },
  {
    eventId: "evt-20260709-kanghui-related-project", eventKey: "603139-related-1225414634", eventType: "related_transaction",
    primaryEntityId: "ent-kanghui", title: "康惠股份子公司拟承接5,059.92万元关联项目",
    summary: "全资子公司中标亿广云数据中心改造项目，交易构成关联交易并待股东会审议。",
    sourceRecordIds: ["src-kanghui-meeting"], evidenceId: "evd-kanghui", factPath: "capital.relatedTransaction",
    evidenceValue: "含税中标价50,599,242.18元，关联股东需回避表决", business: "client_coverage",
    eventStatus: "action_window", signalStatus: "action_window", priority: "high", rmCategory: "治理关系",
    headline: "康惠股份关联项目等待股东会表决", why: "项目金额明确但尚未完成审议，不应提前视为业绩兑现。",
    reasoning: "会议资料明确项目金额、关联关系和审议程序。", metric: { label: "项目金额", value: "5,059.92万元" },
    deadlineAt: "2026-07-16T14:00:00+08:00"
  },
  {
    eventId: "evt-20260709-rainbow-forecast", eventKey: "600707-performance-1225414704", eventType: "performance_forecast",
    primaryEntityId: "ent-rainbow", title: "彩虹股份预计上半年归母净利润同比下降75.66%-78.76%",
    summary: "预计归母净利润0.96亿元至1.10亿元，扣非归母净利润同比下降86.70%至90.15%。",
    sourceRecordIds: ["src-rainbow-forecast"], evidenceId: "evd-rainbow-forecast", factPath: "financial.netProfitForecast",
    evidenceValue: "归母净利润0.96亿元至1.10亿元，同比下降75.66%至78.76%", business: "research_service",
    eventStatus: "risk", signalStatus: "risk", priority: "high", rmCategory: "业绩与分红",
    headline: "彩虹股份上半年盈利预计大幅回落", why: "利润与扣非利润均显著下降，需等待半年报解释经营驱动。",
    reasoning: "官方预告给出利润区间和同比降幅，尚未经审计。", metric: { label: "归母净利润", value: "0.96-1.10亿元" }
  },
  {
    eventId: "evt-20260709-shaanxi-construction-dividend", eventKey: "600248-dividend-1225415542", eventType: "dividend_implementation",
    primaryEntityId: "ent-shaanxi-construction", title: "陕建股份实施2025年度现金分红",
    summary: "每股派发现金红利0.02元，现金红利总额7,427.86万元，7月16日发放。",
    sourceRecordIds: ["src-shaanxi-construction-dividend"], evidenceId: "evd-shaanxi-construction", factPath: "financial.dividend",
    evidenceValue: "每股0.02元，总额74,278,585.72元；7月16日发放", business: "client_coverage",
    eventStatus: "action_window", signalStatus: "action_window", priority: "medium", rmCategory: "业绩与分红",
    headline: "陕建股份现金分红进入实施日程", why: "股权登记和发放日期明确，适合跟踪到账与股东服务节点。",
    reasoning: "权益分派实施公告给出完整日期和金额。", metric: { label: "现金分红总额", value: "7,427.86万元" },
    deadlineAt: "2026-07-16T23:59:00+08:00"
  }
];

for (const row of eventRows) {
  upsert(data.evidence, "evidenceId", {
    evidenceId: row.evidenceId,
    sourceRecordId: row.sourceRecordIds[0],
    factPath: row.factPath,
    value: row.evidenceValue,
    verificationStatus: "verified"
  });
  upsert(data.events, "eventId", {
    eventId: row.eventId,
    eventKey: row.eventKey,
    channel: "listed",
    eventType: row.eventType,
    primaryEntityId: row.primaryEntityId,
    title: row.title,
    summary: row.summary,
    publishedAt: row.eventId.includes("20260709") ? "2026-07-09T00:00:00+08:00" : "2026-07-10T00:00:00+08:00",
    discoveredAt: "2026-07-10T08:20:00+08:00",
    deadlineAt: row.deadlineAt || null,
    lastCheckedAt: "2026-07-10T17:40:00+08:00",
    eventStatus: row.eventStatus,
    noveltyStatus: "new",
    qualityStatus: "verified",
    sourceRecordIds: row.sourceRecordIds,
    evidenceIds: [row.evidenceId],
    business: row.business,
    rmCategory: row.rmCategory,
    metrics: [row.metric],
    timeline: [
      { at: row.eventId.includes("20260709") ? "2026-07-09" : "2026-07-10", label: "公告披露" },
      ...(row.deadlineAt ? [{ at: row.deadlineAt.slice(0, 10), label: "下一公开节点" }] : [])
    ]
  });
  upsert(data.signals, "signalId", {
    signalId: `sig-${row.eventId.replace(/^evt-/, "")}`,
    eventId: row.eventId,
    headline: row.headline,
    whyItMatters: row.why,
    primaryBusiness: row.business,
    priority: row.priority,
    signalStatus: row.signalStatus,
    actionable: Boolean(row.deadlineAt),
    reasoning: row.reasoning
  });
  if (row.deadlineAt) {
    upsert(data.leads, "leadId", {
      leadId: `lead-${row.eventId.replace(/^evt-/, "")}`,
      signalId: `sig-${row.eventId.replace(/^evt-/, "")}`,
      targetEntityId: row.primaryEntityId,
      businessType: row.business,
      opportunityType: row.business === "client_coverage" ? "客户维护" : "研究服务",
      rationale: row.why,
      nextAction: row.eventType === "related_transaction" ? "跟踪股东会表决结果及项目实施进度。" : "核验权益登记、现金发放及到账安排。",
      dueAt: row.deadlineAt,
      leadStatus: "to_assess",
      confidence: "high"
    });
  }
}

const extendEventSources = (eventId, sourceRecordIds) => {
  const event = data.events.find((item) => item.eventId === eventId);
  event.sourceRecordIds = sourceRecordIds;
};
extendEventSources("evt-20260710-machinery-meeting", ["src-machinery-pay", "src-machinery-meeting", "src-machinery-board"]);
extendEventSources("evt-20260709-aikosai-inquiry", ["src-aikosai-sponsor", "src-aikosai-control", "src-aikosai-inquiry", "src-aikosai-accountant"]);

const dailyItems = [
  ["daily-machinery", "evt-20260710-machinery-meeting", "ent-construction-machinery", ["src-machinery-pay", "src-machinery-meeting", "src-machinery-board"], "治理关系", "章程治理", "normal", "同日董事会、股东会通知和薪酬公告归并为一个审议事项"],
  ["daily-bank-litigation", "evt-20260710-bank-litigation", "ent-xian-bank", ["src-bank-litigation"], "风险沟通", "诉讼仲裁", "important", "诉讼进入执行阶段且金额重大"],
  ["daily-bank-director", "evt-20260710-bank-director", "ent-xian-bank", ["src-bank-director"], "治理关系", "董监高", "normal", "监管核准形成治理时间线节点"],
  ["daily-panlong", "evt-20260710-panlong-catalogue", "ent-panlong", ["src-panlong-catalogue"], "经营与产业", "资质许可", "important", "核心产品目录准入可能影响渠道覆盖"],
  ["daily-energy", "evt-20260710-energy-reduction", "ent-shaanxi-energy", ["src-energy-reduction"], "股东服务", "减持", "important", "5%以上股东减持且实施窗口明确"],
  ["daily-meichang", "evt-20260709-meichang-forecast", "ent-meichang", ["src-meichang-forecast"], "业绩与分红", "业绩预告", "important", "半年度业绩预告出现显著增长"],
  ["daily-aikosai", "evt-20260709-aikosai-inquiry", "ent-aikosai", ["src-aikosai-sponsor", "src-aikosai-control", "src-aikosai-inquiry", "src-aikosai-accountant"], "风险沟通", "监管问询", "important", "四份相关公告共同完成年报问询与内控整改核验"],
  ["daily-kanghui", "evt-20260709-kanghui-related-project", "ent-kanghui", ["src-kanghui-meeting"], "经营与产业", "重大合同", "important", "关联交易金额明确且尚待股东会审议"],
  ["daily-rainbow", "evt-20260709-rainbow-forecast", "ent-rainbow", ["src-rainbow-forecast"], "业绩与分红", "业绩预告", "important", "半年度利润预计大幅下降"],
  ["daily-shaanxi-construction", "evt-20260709-shaanxi-construction-dividend", "ent-shaanxi-construction", ["src-shaanxi-construction-dividend"], "业绩与分红", "分红", "normal", "现金分红进入实施阶段并有明确日期"]
].map(([dailyItemId, eventId, entityId, sourceRecordIds, rmCategory, rmSubcategory, importance, inclusionReason]) => {
  const taxonomy = taxonomyTag(rmCategory, rmSubcategory);
  if (!taxonomy) throw new Error(`Unknown listed business taxonomy: ${rmCategory}/${rmSubcategory}`);
  return { dailyItemId, eventId, entityId, sourceRecordIds, rmCategory, rmSubcategory, businessPriority: taxonomy.businessPriority, targetObjects: taxonomy.targetObjects, importance, effective: true, inclusionReason };
});

data.listedDaily = {
  reportDate: "2026-07-10",
  windowStart: "2026-07-09",
  windowEnd: "2026-07-10",
  universeCount: universe.counts.total,
  retrievedUniverseCount: raw._summary.companyUniverseCount,
  universeTierCounts: { L1: universe.counts.L1, L2: universe.counts.L2, L3: universe.counts.L3 },
  universeDataUrl: "../data/listed/universe.json",
  announcementCount: raw._summary.announcementCount,
  coveredCompanyCount: raw._summary.coveredCompanyCount,
  effectiveEventCount: dailyItems.length,
  retrievalErrorCount: raw._summary.errorCount,
  queryMethod: raw._summary.queryMethod,
  sourceStatus: "PASS",
  items: dailyItems
};

data.financialReports = [
  {
    financialReportId: "fin-meichang-2026h1-forecast", eventId: "evt-20260709-meichang-forecast", entityId: "ent-meichang",
    period: "2026H1", disclosureType: "performance_forecast", currency: "CNY", sourceRecordIds: ["src-meichang-forecast"],
    revenue: null, revenueYoY: null, netProfitLower: 295000000, netProfitUpper: 315000000, netProfitYoYLower: 248.45, netProfitYoYUpper: 272.08,
    adjustedNetProfitLower: 265000000, adjustedNetProfitUpper: 285000000, adjustedNetProfitYoYLower: 346.83, adjustedNetProfitYoYUpper: 380.55,
    operatingCashFlow: null, grossMargin: null, netMargin: null, dividendPerShare: null, dividendTotal: null,
    businessMix: ["钨丝金刚线出货占比同比提升超过40%"], anomalies: ["盈利高增长，需等待正式半年报验证现金流和毛利率"], auditStatus: "unaudited"
  },
  {
    financialReportId: "fin-rainbow-2026h1-forecast", eventId: "evt-20260709-rainbow-forecast", entityId: "ent-rainbow",
    period: "2026H1", disclosureType: "performance_forecast", currency: "CNY", sourceRecordIds: ["src-rainbow-forecast"],
    revenue: null, revenueYoY: null, netProfitLower: 96000000, netProfitUpper: 110000000, netProfitYoYLower: -78.76, netProfitYoYUpper: -75.66,
    adjustedNetProfitLower: 40000000, adjustedNetProfitUpper: 54000000, adjustedNetProfitYoYLower: -90.15, adjustedNetProfitYoYUpper: -86.70,
    operatingCashFlow: null, grossMargin: null, netMargin: null, dividendPerShare: null, dividendTotal: null,
    businessMix: [], anomalies: ["归母净利润和扣非净利润均大幅下降"], auditStatus: "unaudited"
  },
  {
    financialReportId: "fin-aikosai-2025a-inquiry", eventId: "evt-20260709-aikosai-inquiry", entityId: "ent-aikosai",
    period: "2025A", disclosureType: "annual_report_inquiry", currency: "CNY", sourceRecordIds: ["src-aikosai-inquiry", "src-aikosai-accountant", "src-aikosai-sponsor", "src-aikosai-control"],
    revenue: 902820200, revenueYoY: -3.48, netProfitLower: -44937100, netProfitUpper: -44937100, netProfitYoYLower: -166.06, netProfitYoYUpper: -166.06,
    adjustedNetProfitLower: null, adjustedNetProfitUpper: null, adjustedNetProfitYoYLower: null, adjustedNetProfitYoYUpper: null,
    operatingCashFlow: null, grossMargin: null, netMargin: null, dividendPerShare: null, dividendTotal: null,
    businessMix: [], anomalies: ["亏损", "收入确认与经销模式被问询", "长账龄应收账款与财务内控需持续观察"], auditStatus: "inquiry_followup"
  },
  {
    financialReportId: "fin-shaanxi-construction-2025-dividend", eventId: "evt-20260709-shaanxi-construction-dividend", entityId: "ent-shaanxi-construction",
    period: "2025A", disclosureType: "dividend_implementation", currency: "CNY", sourceRecordIds: ["src-shaanxi-construction-dividend"],
    revenue: null, revenueYoY: null, netProfitLower: null, netProfitUpper: null, netProfitYoYLower: null, netProfitYoYUpper: null,
    adjustedNetProfitLower: null, adjustedNetProfitUpper: null, adjustedNetProfitYoYLower: null, adjustedNetProfitYoYUpper: null,
    operatingCashFlow: null, grossMargin: null, netMargin: null, dividendPerShare: 0.02, dividendTotal: 74278585.72,
    businessMix: [], anomalies: [], auditStatus: "implemented"
  }
];

for (const snapshot of data.snapshots) {
  snapshot.newEventIds = [...new Set([...snapshot.newEventIds, ...dailyItems.map((item) => item.eventId)])];
}

data.meta.schemaVersion = "0.5";
data.meta.note = "Phase 2上市公司工作台样例：15份公告归并为10个有效事项，并建立4条结构化财务披露记录。";

fs.writeFileSync(samplePath, `${JSON.stringify(data, null, 2)}\n`);
console.log(`Phase 2 sample upgraded: ${data.listedDaily.announcementCount} disclosures, ${data.listedDaily.effectiveEventCount} effective events, ${data.financialReports.length} financial records.`);
