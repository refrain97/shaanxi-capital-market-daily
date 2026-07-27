const DATA_URL = "../data/sample/dashboard-2026-07-10.json";
const TENDER_SOURCES_URL = "../config/tender-sources.json";
const TENDER_RUNTIME_URL = "../data/tender/scans/latest.json";
const PRIVATE_FUND_URL = "../data/private-fund/snapshots/latest.json";
const MA_PROJECTS_URL = "../data/ma-projects/latest.json";
const PRE_IPO_URL = "../data/pre-ipo/latest.json";
const RELATIONSHIPS_URL = "../data/relationships/latest.json";
const ANNUAL_INTELLIGENCE_URL = "../data/annual/2026.json";
const LISTED_TAXONOMY_URL = "../config/listed-business-taxonomy.json";
const LISTED_UNIVERSE_URL = "../data/listed/universe.json";
const LISTED_WORKSPACE_URL = "../data/listed/workspace-2026.json";
const PRIVATE_FUND_WORKSPACE_URL = "../data/private-fund/workspace-2026.json";
const EVENT_STORE_SUMMARY_URL = "../data/runtime/event-store-summary.json";
const BACKFILL_COVERAGE_URL = "../data/backfill/coverage-2026.json";
const WATCH_STORAGE_KEY = "shaanxi-v3-watch-items-v1";

const labels = {
  channels: {
    listed: { name: "上市公司", icon: "landmark", description: "公告、财务、治理与风险" },
    private_fund: { name: "证券私募", icon: "users", description: "机构、人员、产品和状态" },
    equity_financing: { name: "股权融资", icon: "circle-dollar-sign", description: "产业基金、拟上市和Pre-IPO" },
    ma: { name: "收并购", icon: "git-merge", description: "交易结构、进度与交割" },
    tender: { name: "金融招投标", icon: "file-check-2", description: "公告期机会、截止与结果" },
    soe: { name: "国企雷达", icon: "radar", description: "资本、项目与主体动态" }
  },
  business: {
    client_coverage: "客户维护",
    risk_service: "风险服务",
    research_service: "研究服务",
    private_fund_service: "私募服务",
    equity_financing: "股权融资",
    investment_banking: "投行服务",
    ma_advisory: "并购财顾",
    bond_financing: "债券融资"
  },
  status: {
    action_window: "行动窗口", progressing: "进展中", watch: "观察", risk: "风险",
    active: "存续", completed: "已完成", today_new: "今日新增", data_update: "数据更新",
    result_progress: "结果进展", backfill: "回溯补录", unchanged: "无变化"
  },
  leadStatus: {
    to_assess: "待判断", to_contact: "待联系", following: "跟进中", waiting: "等待节点",
    converted: "已转化", closed: "已关闭"
  },
  watchStatus: {
    saved: "已收藏", to_review: "待复核", following: "跟进中", waiting: "等待节点",
    resolved: "已解决", closed: "已结束"
  },
  disclosureType: {
    annual_report: "年报", quarterly_report: "季报", performance_forecast: "业绩预告",
    performance_flash: "业绩快报", annual_report_inquiry: "年报问询", dividend_implementation: "分红实施"
  },
  auditStatus: {
    audited: "已审计", unaudited: "未经审计", inquiry_followup: "问询跟踪", implemented: "已实施"
  }
};

const state = {
  data: null,
  slot: "morning",
  view: "dashboard",
  signalFilters: { channel: "all", status: "all", query: "" },
  annualFilters: { channel: "all", status: "all", business: "all", query: "" },
  watchFilters: { channel: "all", status: "all", priority: "all", query: "" },
  listedFilters: { query: "", category: "all", importance: "all" },
  listedTab: "daily",
  listedFinancialMode: "table",
  listedPeriod: "all",
  listedCompareIds: ["ent-meichang", "ent-rainbow", "ent-aikosai"],
  listedCompanyId: null,
  listedWorkspace: null,
  listedWorkspaceStatus: "active",
  listedWorkspaceLimit: 60,
  tenderRegistry: null,
  tenderRuntime: null,
  tenderTab: "opportunities",
  privateFund: null,
  privateTab: "filings",
  privateWorkspace: null,
  privateOpenQuarters: new Set(["Q3"]),
  maProjects: null,
  preIpo: null,
  relationships: null,
  annualIntelligence: null,
  listedTaxonomy: null,
  listedUniverse: null,
  eventStore: null,
  backfillCoverage: null,
  dealsTab: "projects",
  dealsStage: "all",
  dealsQuery: "",
  preIpoQuery: "",
  watchItems: [],
  entityQuery: "",
  entityTab: "directory",
  relationType: "all"
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const entityById = (id) => state.data.entities.find((item) => item.entityId === id);
const eventById = (id) => state.data.events.find((item) => item.eventId === id);
const signalByEvent = (id) => state.data.signals.find((item) => item.eventId === id);
const signalById = (id) => state.data.signals.find((item) => item.signalId === id);
const leadBySignal = (id) => state.data.leads.find((item) => item.signalId === id);
const watchByEvent = (id) => state.watchItems.find((item) => item.eventId === id);
const currentSnapshot = () => state.data.snapshots.find((item) => item.slot === state.slot);
const priorityRank = { high: 0, medium: 1, low: 2 };
const activeWatchStatuses = new Set(["saved", "to_review", "following", "waiting"]);
const validWatchStatuses = new Set([...activeWatchStatuses, "resolved", "closed"]);

function isValidWatchItem(item) {
  const event = item && eventById(item.eventId);
  const history = item?.stateHistory;
  return Boolean(
    event && entityById(item.entityId) && event.primaryEntityId === item.entityId &&
    validWatchStatuses.has(item.watchStatus) && priorityRank[item.priority] !== undefined &&
    Array.isArray(item.tags) && typeof item.note === "string" &&
    Number.isFinite(Date.parse(item.createdAt)) && Number.isFinite(Date.parse(item.updatedAt)) &&
    Date.parse(item.updatedAt) >= Date.parse(item.createdAt) &&
    (!activeWatchStatuses.has(item.watchStatus) || Number.isFinite(Date.parse(item.nextReviewAt))) &&
    Array.isArray(history) && history.length > 0 && history.at(-1).status === item.watchStatus
  );
}

function icon(name, className = "") {
  return `<i data-lucide="${name}" class="${className}"></i>`;
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "aria-hidden": "true" } });
}

function shortDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function dateLabel(value) {
  if (!value) return "--";
  const date = new Date(value);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function formatMoney(value, currency = "CNY") {
  if (value === null || value === undefined) return "--";
  const sign = value < 0 ? "-" : "";
  const absolute = Math.abs(value);
  const prefix = currency === "CNY" ? "¥" : currency === "HKD" ? "HK$" : "$";
  if (absolute >= 100000000) return `${sign}${prefix}${(absolute / 100000000).toFixed(2)}亿`;
  if (absolute >= 10000) return `${sign}${prefix}${(absolute / 10000).toFixed(2)}万`;
  return `${sign}${prefix}${absolute.toLocaleString("zh-CN")}`;
}

function formatRange(lower, upper, currency = "CNY") {
  if (lower === null && upper === null) return "--";
  if (lower === upper) return formatMoney(lower, currency);
  const prefix = currency === "CNY" ? "¥" : currency === "HKD" ? "HK$" : "$";
  const maximum = Math.max(Math.abs(lower || 0), Math.abs(upper || 0));
  const divisor = maximum >= 100000000 ? 100000000 : maximum >= 10000 ? 10000 : 1;
  const unit = divisor === 100000000 ? "亿" : divisor === 10000 ? "万" : "";
  const render = (value) => `${value < 0 ? "-" : ""}${prefix}${(Math.abs(value) / divisor).toFixed(divisor === 1 ? 0 : 2)}${unit}`;
  return `${render(lower)}–${render(upper)}`;
}

function formatPercentRange(lower, upper) {
  if (lower === null && upper === null) return "--";
  const format = (value) => `${value > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
  return lower === upper ? format(lower) : `${format(lower)}–${format(upper)}`;
}

function daysFromSnapshot(value) {
  const base = new Date(`${currentSnapshot().date}T00:00:00+08:00`);
  return Math.max(0, Math.ceil((new Date(value) - base) / 86400000));
}

function badgeForStatus(status) {
  const color = status === "risk" ? "red" : status === "action_window" ? "amber" : status === "completed" || status === "result_progress" ? "green" : status === "backfill" ? "purple" : "blue";
  return `<span class="badge ${color}">${esc(labels.status[status] || status)}</span>`;
}

function qualityBadge(status) {
  const map = { verified: ["已回源", "green"], cross_checked: ["交叉核验", "amber"], pending: ["待核验", "amber"], conflict: ["口径冲突", "red"] };
  const [label, color] = map[status] || [status, ""];
  return `<span class="badge ${color}">${esc(label)}</span>`;
}

function watchBadge(status) {
  const color = status === "following" ? "blue" : status === "waiting" || status === "to_review" ? "amber" : status === "resolved" || status === "closed" ? "green" : "purple";
  return `<span class="badge ${color}">${esc(labels.watchStatus[status] || status)}</span>`;
}

function loadWatchItems() {
  const stored = localStorage.getItem(WATCH_STORAGE_KEY);
  if (stored === null) {
    state.watchItems = structuredClone(state.data.watchItems || []);
    persistWatchItems();
    return;
  }
  try {
    const parsed = JSON.parse(stored);
    const seenEvents = new Set();
    state.watchItems = Array.isArray(parsed) ? parsed.filter((item) => {
      if (!isValidWatchItem(item) || seenEvents.has(item.eventId)) return false;
      seenEvents.add(item.eventId);
      return true;
    }) : [];
    if (state.watchItems.length !== parsed.length) persistWatchItems();
  } catch {
    state.watchItems = structuredClone(state.data.watchItems || []);
    persistWatchItems();
  }
}

function persistWatchItems() {
  localStorage.setItem(WATCH_STORAGE_KEY, JSON.stringify(state.watchItems));
  updateWatchCount();
}

function updateWatchCount() {
  const active = state.watchItems.filter((item) => !["resolved", "closed"].includes(item.watchStatus)).length;
  const count = $("#navWatchCount");
  if (count) count.textContent = active;
}

function toDateTimeInput(value) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function pageHeading(eyebrow, title, subtitle, meta = "") {
  return `<div class="page-heading"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-meta">${meta}</div></div>`;
}

function signalRow(signal) {
  const event = eventById(signal.eventId);
  const entity = entityById(event.primaryEntityId);
  const metric = event.metrics?.[0];
  const watched = Boolean(watchByEvent(event.eventId));
  return `<article class="signal-row" data-event-id="${event.eventId}">
    <span class="signal-stripe ${signal.priority}"></span>
    <div class="signal-copy">
      <div class="signal-meta">${badgeForStatus(signal.signalStatus)}<span>${labels.channels[event.channel].name}</span><span>${esc(entity.canonicalName)}</span><span>${labels.business[signal.primaryBusiness] || signal.primaryBusiness}</span></div>
      <h3>${esc(signal.headline)}</h3><p>${esc(signal.whyItMatters)}</p>
    </div>
    <div class="signal-metrics"><button class="row-watch ${watched ? "saved" : ""}" data-watch-event="${event.eventId}" title="${watched ? "取消跟踪" : "加入跟踪"}" aria-label="${watched ? "取消跟踪" : "加入跟踪"}">${icon(watched ? "bookmark-check" : "bookmark")}</button>${metric ? `<strong>${esc(metric.value)}</strong><span>${esc(metric.label)}</span>` : `<strong>已回源</strong><span>${event.qualityStatus}</span>`}</div>
  </article>`;
}

function renderDashboard() {
  const deepRead = state.listedWorkspace?.deepRead;
  const latestItems = getListedDeepReads(true);
  const latestDate = deepRead?.latestReportDate || state.privateFund?.asOf?.slice(0, 10) || currentSnapshot().date;
  const importanceScore = (item) => Number(Boolean(item.importanceNote)) * 100 + Number(item.rmSubcategories.includes("债务融资")) * 30 + item.verifiedNumbers.length;
  const important = [...latestItems].sort((a, b) => importanceScore(b) - importanceScore(a)).slice(0, 6);
  const actions = latestItems.filter((item) => item.nextAction).slice(0, 6);
  const listedCount = state.listedUniverse?.counts.total ?? 0;
  const managerCount = state.privateFund?.summary.observationManagerCount ?? state.privateFund?.summary.managerCount ?? 0;
  const productCount = state.privateFund?.summary.ytdProductCount ?? state.privateWorkspace?.summary.productCount ?? 0;
  const maCount = state.maProjects?.projectCount ?? 0;
  const reserveCount = state.preIpo?.reserveTotalCount ?? 0;
  const tenderCount = state.tenderRuntime?.summary.activeOpportunityCount ?? 0;
  const highlightRows = important.map((item) => `<article class="customer-highlight-card" data-listed-deep-read="${esc(item.deepReadId)}">
    <div class="signal-meta"><span class="badge green">${esc(item.companyName)}</span><span>${esc(item.primarySectionName)}</span><span>${esc(item.securityCode)}</span></div>
    <h3>${esc(item.title)}</h3><p>${esc(item.summary)}</p>
    ${item.verifiedNumbers.length ? `<div class="deep-read-numbers">${icon("binary")}${esc(item.verifiedNumbers.slice(0, 5).join(" / "))}</div>` : ""}
    <small>${esc(item.businessJudgement)}</small>
  </article>`).join("");
  const actionRows = actions.map((item) => `<button class="customer-action-row" data-listed-deep-read="${esc(item.deepReadId)}"><span>${dateLabel(item.reportDate)}</span><div><strong>${esc(item.companyName)}</strong><p>${esc(item.nextAction)}</p></div>${icon("chevron-right")}</button>`).join("");
  const scopeRows = [
    ["listed", "landmark", "上市公司", `${listedCount}家`, `最新${latestItems.length}项重点动态`],
    ["private", "users", "证券私募", `${managerCount}家`, `年内${productCount}只产品备案`],
    ["deals", "git-merge", "并购与融资", `${maCount}项`, "按交易阶段跟踪"],
    ["deals", "building-2", "上市后备", `${reserveCount}家`, `A档${state.preIpo?.aTierTranscribedCount ?? 0}家`],
    ["tender", "file-clock", "招投标机会", `${tenderCount}项`, "当前公告期机会"],
  ].map(([view, iconName, name, value, note]) => `<button class="customer-scope-card" data-view="${view}"><span class="channel-icon">${icon(iconName)}</span><div><strong>${name}</strong><p>${note}</p></div><b>${value}</b></button>`).join("");

  $("#view-dashboard").innerHTML = `
    ${pageHeading(`截至${dateLabel(latestDate)}`, "陕西资本市场日报", "汇总上市公司、证券私募、并购融资与金融服务机会。", `公开信息整理<br>仅供参考`)}
    <div class="kpi-grid customer-kpis">
      ${kpi("上市公司观察", listedCount, "landmark", "家", "listed")}
      ${kpi("本期公司事项", latestItems.length, "newspaper", "项", "listed")}
      ${kpi("私募管理人观察", managerCount, "users", "家", "private")}
      ${kpi("年内备案产品", productCount, "layers-3", "只", "private")}
      ${kpi("并购项目跟踪", maCount, "git-merge", "项", "deals")}
    </div>
    <div class="customer-dashboard-grid">
      <section class="panel"><div class="panel-head"><h2>重点动态</h2><button data-view="listed">查看上市公司日报 ${icon("arrow-right")}</button></div><div class="customer-highlight-grid">${highlightRows || emptyState("本期暂无重点动态")}</div></section>
      <section class="panel"><div class="panel-head"><h2>近期关注</h2><span>${actions.length}个后续节点</span></div><div class="customer-action-list">${actionRows || emptyState("暂无待跟踪节点")}</div></section>
    </div>
    <section class="panel customer-scope"><div class="panel-head"><h2>观察范围</h2><span>按主体与项目持续更新</span></div><div class="customer-scope-grid">${scopeRows}</div></section>
    <section class="soe-feature"><div><span class="eyebrow">陕西国企动态</span><h2>陕西西安国企动态雷达</h2><p>聚焦资本运作、重点项目、资产交易与风险治理动态。</p></div><a href="../../soe-radar/index.html" target="_blank" rel="noreferrer">查看国企动态 ${icon("external-link")}</a></section>`;
}

function renderListed() {
  const daily = state.data.listedDaily;
  const workspace = state.listedWorkspace;
  const targetCount = state.listedUniverse?.counts.total ?? daily.universeCount;
  const tabs = [
    ["daily", "最新日报", "重点事项与关键数字"],
    ["important", "持续关注", "存续事项与下一节点"],
    ["financial", "财务报告", "结构化比较"],
    ["company", "公司跟踪", "事件与复核"]
  ];
  const tabBar = `<div class="workspace-tabs" role="tablist">${tabs.map(([value, label, sub]) => `<button class="${state.listedTab === value ? "active" : ""}" data-listed-tab="${value}" role="tab" aria-selected="${state.listedTab === value}"><strong>${label}</strong><span>${sub}</span></button>`).join("")}</div>`;
  const content = state.listedTab === "financial" ? renderListedFinancial() : state.listedTab === "company" ? renderListedCompany() : renderListedDeepReadWorkspace(state.listedTab === "daily");
  const retrieved = workspace?.universe.retrievedSubjectCount ?? daily.retrievedUniverseCount;
  const latestDeepRead = workspace?.deepRead?.latestReportDate || daily.reportDate;
  $("#view-listed").innerHTML = `${pageHeading("上市公司", "陕西上市公司日报", `覆盖${targetCount}家重点观察公司，呈现公告事实、关键数字、影响判断与后续节点。`, `已覆盖 ${retrieved} 家<br>最新日报 ${latestDeepRead}`)}${tabBar}${content}`;
  bindListedControls();
}

function listedKpis() {
  const daily = state.data.listedDaily;
  const workspace = state.listedWorkspace;
  const universe = workspace?.universe;
  const targetCount = universe?.targetCount ?? state.listedUniverse?.counts.total ?? daily.universeCount;
  const retrievedCount = universe?.retrievedSubjectCount ?? daily.retrievedUniverseCount;
  const announcements = universe?.announcementCount ?? daily.announcementCount;
  const deepRead = workspace?.deepRead;
  const deepReadCount = deepRead?.deepReadItemCount ?? daily.effectiveEventCount;
  const pdfVerifiedCount = deepRead?.pdfVerifiedItemCount ?? 0;
  const tierMap = Object.fromEntries((universe?.tierStats || []).map((item) => [item.tier, item]));
  const tierCounts = state.listedUniverse?.counts ?? daily.universeTierCounts;
  const coverageText = retrievedCount === targetCount ? `${targetCount}家均有检索返回` : `目标${targetCount}家，当前返回${retrievedCount}家`;
  return `<div class="kpi-grid listed-kpis"><div class="kpi"><span class="kpi-top"><span>观察公司</span>${icon("layers-3")}</span><strong class="kpi-value">${targetCount}<span class="kpi-delta">家</span></strong></div><div class="kpi"><span class="kpi-top"><span>已覆盖公司</span>${icon("scan-search")}</span><strong class="kpi-value">${retrievedCount}<span class="kpi-delta">${retrievedCount}/${targetCount}</span></strong></div><div class="kpi"><span class="kpi-top"><span>年内公告</span>${icon("files")}</span><strong class="kpi-value">${announcements}<span class="kpi-delta">份</span></strong></div><div class="kpi"><span class="kpi-top"><span>重点事项</span>${icon("book-open-check")}</span><strong class="kpi-value">${deepReadCount}<span class="kpi-delta">项</span></strong></div><div class="kpi"><span class="kpi-top"><span>已核验关键数字</span>${icon("badge-check")}</span><strong class="kpi-value">${pdfVerifiedCount}<span class="kpi-delta">项</span></strong></div></div><div class="listed-universe-strip"><div><strong>L1 · ${tierMap.L1?.subjectCount ?? tierCounts.L1}</strong><span>${tierMap.L1?.announcementCount ?? "--"}份公告</span></div><div><strong>L2 · ${tierMap.L2?.subjectCount ?? tierCounts.L2}</strong><span>${tierMap.L2?.announcementCount ?? "--"}份公告</span></div><div><strong>L3 · ${tierMap.L3?.subjectCount ?? tierCounts.L3}</strong><span>${tierMap.L3?.announcementCount ?? "--"}份公告</span></div><p>${icon("circle-check-big")}${coverageText}；重点事项均附公告原文与后续关注节点。</p></div>`;
}

function getListedDailyItems(importantOnly = false) {
  let items = state.data.listedDaily.items.map((item) => ({ ...item, event: eventById(item.eventId), entity: entityById(item.entityId) }));
  const filters = state.listedFilters;
  if (importantOnly) items = items.filter((item) => item.businessPriority === "focus" || item.importance === "important");
  if (filters.importance === "business_focus") items = items.filter((item) => item.businessPriority === "focus");
  else if (filters.importance !== "all") items = items.filter((item) => item.importance === filters.importance);
  if (filters.category !== "all") items = items.filter((item) => item.rmCategory === filters.category);
  if (filters.query) {
    const query = filters.query.toLowerCase();
    items = items.filter((item) => `${item.entity.canonicalName}${item.entity.securityCode}${item.event.title}${item.event.summary}${item.rmCategory}${item.rmSubcategory}${item.targetObjects.join("")}`.toLowerCase().includes(query));
  }
  return items.sort((a, b) => Number(b.businessPriority === "focus") - Number(a.businessPriority === "focus") || Number(b.importance === "important") - Number(a.importance === "important") || new Date(b.event.publishedAt) - new Date(a.event.publishedAt));
}

function renderListedDaily(importantOnly) {
  const items = getListedDailyItems(importantOnly);
  const categories = state.listedTaxonomy?.categories.map((item) => item.name) || ["资本运作", "股东服务", "激励与员工", "资金与财务", "治理关系", "风险沟通", "业绩与分红", "经营与产业"];
  const toolbar = `<div class="toolbar listed-toolbar" data-filter-kind="listed"><label class="search-field">${icon("search")}<input type="search" data-listed-filter="query" value="${esc(state.listedFilters.query)}" placeholder="搜索公司、代码、二级标签或跟进对象"></label><select data-listed-filter="category">${option("all", "全部RM分类", state.listedFilters.category)}${categories.map((value) => option(value, value, state.listedFilters.category)).join("")}</select>${importantOnly ? "" : `<select data-listed-filter="importance">${option("all", "全部事项", state.listedFilters.importance)}${option("business_focus", "业务重点", state.listedFilters.importance)}${option("important", "内容重要", state.listedFilters.importance)}${option("normal", "一般有效事项", state.listedFilters.importance)}</select>`}</div>`;
  return `${listedKpis()}<div class="listed-context"><span>${importantOnly ? "双轴重点筛选" : "完整日报口径"}</span><strong>${items.length} 个有效事项</strong><p>${importantOnly ? "业务重点严格按确认的21个二级标签；内容重要性继续独立判断风险、业绩异常和重大经营事项。" : "公告先归并为唯一事项，再分别标注一级业务、二级标签、业务重点和内容重要性。"}</p></div>${toolbar}<div class="listed-daily-list">${items.map(listedDailyRow).join("") || emptyState("当前筛选无有效事项")}</div>`;
}

function getListedDeepReads(latestOnly = false) {
  const deepRead = state.listedWorkspace?.deepRead;
  if (!deepRead) return [];
  const activeNames = new Set((state.listedUniverse?.entities || []).map((item) => item.canonicalName));
  let items = deepRead.items.filter((item) => !activeNames.size || activeNames.has(item.companyName));
  if (latestOnly) items = items.filter((item) => item.reportDate === deepRead.latestReportDate);
  else items = items.filter((item) => item.workspaceStatus === state.listedWorkspaceStatus);
  const filters = state.listedFilters;
  if (filters.category !== "all") items = items.filter((item) => item.rmCategories.includes(filters.category));
  if (filters.query) {
    const query = filters.query.toLowerCase();
    items = items.filter((item) => `${item.companyName}${item.securityCode}${item.title}${item.summary}${item.businessJudgement}${item.nextAction}${item.rmCategories.join("")}${item.rmSubcategories.join("")}`.toLowerCase().includes(query));
  }
  return items;
}

function renderListedDeepReadWorkspace(latestOnly) {
  const deepRead = state.listedWorkspace?.deepRead;
  if (!deepRead) return `${listedKpis()}${emptyState("上市公司数据加载失败")}`;
  const items = getListedDeepReads(latestOnly);
  const visible = items.slice(0, state.listedWorkspaceLimit);
  const categories = state.listedTaxonomy?.categories.map((item) => item.name) || [];
  const statusSwitch = latestOnly ? "" : `<div class="workspace-status-switch" role="group" aria-label="事项状态"><button class="${state.listedWorkspaceStatus === "active" ? "active" : ""}" data-listed-workspace-status="active">${icon("radio-tower")}持续跟踪 <strong>${deepRead.activeItemCount}</strong></button><button class="${state.listedWorkspaceStatus === "archived" ? "active" : ""}" data-listed-workspace-status="archived">${icon("archive")}已结束归档 <strong>${deepRead.archivedItemCount}</strong></button></div>`;
  const toolbar = `<div class="toolbar listed-toolbar"><label class="search-field">${icon("search")}<input type="search" data-listed-filter="query" value="${esc(state.listedFilters.query)}" placeholder="搜索公司、正文事实、关键数字或下一节点"></label><select data-listed-filter="category">${option("all", "全部8类业务", state.listedFilters.category)}${categories.map((value) => option(value, value, state.listedFilters.category)).join("")}</select></div>`;
  const rows = visible.map(listedDeepReadRow).join("");
  const more = visible.length < items.length ? `<button class="load-more" data-listed-load-more>${icon("chevrons-down")}再显示 ${Math.min(60, items.length - visible.length)} 项</button>` : "";
  const context = latestOnly
    ? `<div class="listed-context verified"><span>${icon("book-open-check")}最新日报</span><strong>${deepRead.latestReportDate} · ${items.length}项重点事项</strong><p>核心事实、关键数字和公告原文已统一整理，可点击查看详情。</p></div>`
    : `<div class="listed-context verified"><span>${icon("shield-check")}持续关注</span><strong>${deepRead.reportCount}个日报日期 · ${items.length}项当前事项</strong><p>按公司、事项类型和跟踪状态查看后续进展。</p></div>`;
  return `${listedKpis()}${context}${statusSwitch}${toolbar}<div class="listed-workspace-list">${rows || emptyState("当前筛选没有精读事项")}</div>${more}`;
}

function listedDeepReadRow(item) {
  const status = item.workspaceStatus === "archived" ? '<span class="badge gray">已归档</span>' : '<span class="badge green">持续跟踪</span>';
  const evidence = item.evidenceLevel === "PDF正文数字已核验" ? '<span class="badge blue">关键数字已核验</span>' : '<span class="badge amber">公告原文已核验</span>';
  const categories = [...item.rmCategories, ...item.rmSubcategories].filter((value) => value && value !== "未归类").slice(0, 3).join(" · ");
  const numbers = item.verifiedNumbers.slice(0, 4).join(" / ");
  return `<article class="listed-workspace-row listed-deep-read-row" data-listed-deep-read="${esc(item.deepReadId)}"><div class="listed-date"><strong>${dateLabel(item.reportDate)}</strong><span>${esc(item.securityCode)}</span></div><div class="listed-event"><div class="signal-meta">${status}${evidence}<span>${esc(item.primarySectionName)}</span></div><h3>${esc(item.title)}</h3><p>${esc(item.summary)}</p>${numbers ? `<div class="deep-read-numbers">${icon("binary")}${esc(numbers)}</div>` : ""}<small><b>影响判断</b> ${esc(item.businessJudgement)}${item.nextAction ? `<br><b>后续关注</b> ${esc(item.nextAction)}` : ""}</small></div><div class="listed-workspace-action"><strong>${item.sourceCount}份公告原文</strong><span>${esc(categories || "重点事项")}</span><button class="text-button" data-listed-deep-read="${esc(item.deepReadId)}">${icon("panel-right-open")}查看详情</button></div></article>`;
}

function openListedDeepRead(deepReadId) {
  const item = state.listedWorkspace?.deepRead?.items.find((row) => row.deepReadId === deepReadId);
  if (!item) return;
  $("#drawerEyebrow").textContent = `${item.reportDate} · ${item.primarySectionName}`;
  $("#drawerTitle").textContent = item.title;
  $("#drawerWatch").style.display = "none";
  const numbers = item.verifiedNumbers.length ? `<section class="detail-section"><h3>原文关键数字</h3><div class="deep-read-number-grid">${item.verifiedNumbers.map((value) => `<span>${esc(value)}</span>`).join("")}</div></section>` : "";
  const supporting = item.supportingInsights.length ? `<section class="detail-section"><h3>同一事项补充信息</h3>${item.supportingInsights.map((row) => `<div class="deep-read-support"><strong>${esc(row.title)}</strong><p>${esc(row.summary)}</p></div>`).join("")}</section>` : "";
  const sources = item.sources.map((source, index) => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer"><span>${String(index + 1).padStart(2, "0")}</span><strong>${esc(source.title)}</strong>${icon("external-link")}</a>`).join("");
  const importance = item.importanceNote ? `<div class="deep-read-highlight"><strong>重点摘要</strong><br>${esc(item.importanceNote)}</div>` : "";
  $("#drawerBody").innerHTML = `<section class="detail-section"><div class="signal-meta"><span class="badge green">公告原文已核验</span><span>${item.sourceCount}份公告</span><span>${esc(item.securityCode)}</span></div><p class="detail-summary">${esc(item.summary)}</p>${importance}</section><section class="detail-section"><h3>影响判断与后续关注</h3><div class="judgement"><strong>影响判断</strong><br>${esc(item.businessJudgement)}</div>${item.nextAction ? `<div class="next-action"><strong>后续关注</strong><br>${esc(item.nextAction)}</div>` : ""}</section>${numbers}${supporting}<section class="detail-section"><h3>公告原文 · ${item.sourceCount}份</h3><div class="source-link-list">${sources || emptyState("原文链接待补")}</div></section>`;
  document.body.classList.add("drawer-open");
  $("#detailDrawer").setAttribute("aria-hidden", "false");
  refreshIcons();
}

function listedDailyRow(item) {
  const signal = signalByEvent(item.eventId);
  const watched = Boolean(watchByEvent(item.eventId));
  const priorityBadges = `${item.businessPriority === "focus" ? '<span class="badge green">业务重点</span>' : ""}${item.importance === "important" ? '<span class="badge red">内容重要</span>' : item.businessPriority !== "focus" ? '<span class="badge blue">有效</span>' : ""}`;
  return `<article class="listed-daily-row" data-event-id="${item.eventId}"><div class="listed-date"><strong>${dateLabel(item.event.publishedAt)}</strong><span>${item.sourceRecordIds.length}份公告</span></div><div class="listed-event"><div class="signal-meta">${priorityBadges}<span>${esc(item.rmCategory)} · ${esc(item.rmSubcategory)}</span><span>${esc(item.entity.securityCode || item.entity.universeTier)}</span></div><h3>${esc(item.entity.canonicalName)}｜${esc(item.event.title)}</h3><p>${esc(item.event.summary)}</p><small>${esc(item.inclusionReason)} · 跟进对象：${esc(item.targetObjects.join("、"))}</small></div><div class="listed-action"><button class="row-watch ${watched ? "saved" : ""}" data-watch-event="${item.eventId}" title="${watched ? "取消跟踪" : "加入跟踪"}" aria-label="${watched ? "取消跟踪" : "加入跟踪"}">${icon(watched ? "bookmark-check" : "bookmark")}</button>${badgeForStatus(signal?.signalStatus || item.event.eventStatus)}<strong>${esc(item.event.metrics?.[0]?.value || "已回源")}</strong><span>${esc(item.event.metrics?.[0]?.label || "来源完整")}</span></div></article>`;
}

function getFinancialReports() {
  return state.data.financialReports.filter((item) => state.listedPeriod === "all" || item.period === state.listedPeriod);
}

function renderListedFinancial() {
  const reports = getFinancialReports();
  const periods = [...new Set(state.data.financialReports.map((item) => item.period))];
  const mode = `<div class="financial-controls"><div class="segmented-control" role="group" aria-label="财务展示模式"><button class="${state.listedFinancialMode === "table" ? "active" : ""}" data-financial-mode="table">财务表</button><button class="${state.listedFinancialMode === "compare" ? "active" : ""}" data-financial-mode="compare">公司比较</button></div><select id="listedPeriod">${option("all", "全部报告期", state.listedPeriod)}${periods.map((value) => option(value, value, state.listedPeriod)).join("")}</select></div>`;
  return `${mode}${state.listedFinancialMode === "compare" ? renderFinancialCompare(reports) : renderFinancialTable(reports)}`;
}

function renderFinancialTable(reports) {
  const rows = reports.map((report) => {
    const entity = entityById(report.entityId);
    const anomaly = report.anomalies.join("；") || "无异常标记";
    return `<tr data-event-id="${report.eventId}"><td><strong>${esc(entity.canonicalName)}</strong><br><span class="eyebrow">${esc(entity.securityCode)} · ${entity.universeTier}</span></td><td>${esc(report.period)}</td><td>${labels.disclosureType[report.disclosureType]}</td><td>${formatMoney(report.revenue, report.currency)}</td><td class="${report.revenueYoY < 0 ? "negative" : "positive"}">${report.revenueYoY === null ? "--" : formatPercentRange(report.revenueYoY, report.revenueYoY)}</td><td>${formatRange(report.netProfitLower, report.netProfitUpper, report.currency)}</td><td class="${report.netProfitYoYUpper < 0 ? "negative" : "positive"}">${formatPercentRange(report.netProfitYoYLower, report.netProfitYoYUpper)}</td><td>${formatRange(report.adjustedNetProfitLower, report.adjustedNetProfitUpper, report.currency)}</td><td>${report.dividendPerShare === null ? "--" : `${formatMoney(report.dividendPerShare, report.currency)}/股`}</td><td class="financial-anomaly">${esc(anomaly)}</td><td>${labels.auditStatus[report.auditStatus]}</td></tr>`;
  }).join("");
  return `<div class="financial-note">金额按原公告币种展示，空值表示本次披露未提供；不同币种和不同报告期不做合计。</div><div class="data-table-wrap"><table class="data-table financial-table"><thead><tr><th>公司</th><th>报告期</th><th>披露类型</th><th>营业收入</th><th>营收同比</th><th>归母净利润</th><th>归母同比</th><th>扣非净利润</th><th>每股分红</th><th>异常项</th><th>口径状态</th></tr></thead><tbody>${rows || `<tr><td colspan="11" class="empty-row">当前报告期无财务披露</td></tr>`}</tbody></table></div>`;
}

function renderFinancialCompare(reports) {
  const available = state.data.financialReports;
  const selected = available.filter((item) => state.listedCompareIds.includes(item.entityId) && (state.listedPeriod === "all" || item.period === state.listedPeriod));
  const pickers = available.map((report) => {
    const entity = entityById(report.entityId);
    const active = state.listedCompareIds.includes(report.entityId);
    return `<button class="compare-chip ${active ? "active" : ""}" data-compare-entity="${report.entityId}">${icon(active ? "check" : "plus")}${esc(entity.canonicalName)}<span>${esc(report.period)}</span></button>`;
  }).join("");
  const metrics = [
    ["披露类型", (item) => labels.disclosureType[item.disclosureType]],
    ["营业收入", (item) => formatMoney(item.revenue, item.currency)],
    ["营收同比", (item) => formatPercentRange(item.revenueYoY, item.revenueYoY)],
    ["归母净利润", (item) => formatRange(item.netProfitLower, item.netProfitUpper, item.currency)],
    ["归母同比", (item) => formatPercentRange(item.netProfitYoYLower, item.netProfitYoYUpper)],
    ["扣非净利润", (item) => formatRange(item.adjustedNetProfitLower, item.adjustedNetProfitUpper, item.currency)],
    ["每股分红", (item) => item.dividendPerShare === null ? "--" : `${formatMoney(item.dividendPerShare, item.currency)}/股`],
    ["异常项", (item) => item.anomalies.join("；") || "无异常标记"]
  ];
  const header = selected.map((report) => `<th>${esc(entityById(report.entityId).canonicalName)}<span>${esc(report.period)} · ${report.currency}</span></th>`).join("");
  const body = metrics.map(([label, getter]) => `<tr><th>${label}</th>${selected.map((report) => `<td>${esc(getter(report))}</td>`).join("")}</tr>`).join("");
  return `<div class="compare-picker">${pickers}</div>${selected.length ? `<div class="compare-grid-wrap"><table class="compare-grid"><thead><tr><th>指标</th>${header}</tr></thead><tbody>${body}</tbody></table></div>` : emptyState("请选择至少一家公司进行比较")}`;
}

function renderListedCompany() {
  const entityIds = [...new Set(state.data.listedDaily.items.map((item) => item.entityId))];
  if (!state.listedCompanyId || !entityIds.includes(state.listedCompanyId)) state.listedCompanyId = entityIds[0];
  const selected = entityById(state.listedCompanyId);
  const events = state.data.events.filter((item) => item.primaryEntityId === selected.entityId).sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt));
  const dailyItems = state.data.listedDaily.items.filter((item) => item.entityId === selected.entityId);
  const reports = state.data.financialReports.filter((item) => item.entityId === selected.entityId);
  const watches = state.watchItems.filter((item) => item.entityId === selected.entityId);
  const index = entityIds.map((entityId) => {
    const entity = entityById(entityId);
    const count = state.data.listedDaily.items.filter((item) => item.entityId === entityId).reduce((sum, item) => sum + item.sourceRecordIds.length, 0);
    return `<button class="company-index-row ${entityId === selected.entityId ? "active" : ""}" data-listed-company="${entityId}"><span><strong>${esc(entity.canonicalName)}</strong><small>${esc(entity.securityCode)} · ${entity.universeTier}</small></span><b>${count}</b></button>`;
  }).join("");
  const timeline = events.map((event) => `<button class="company-event-row" data-event-id="${event.eventId}"><span>${dateLabel(event.publishedAt)}</span><div><strong>${esc(event.title)}</strong><small>${esc(event.summary)}</small></div>${badgeForStatus(event.eventStatus)}</button>`).join("");
  return `<div class="company-workbench"><aside class="company-index"><div class="company-index-head"><strong>本期发布公司</strong><span>${entityIds.length}家</span></div>${index}</aside><section class="company-profile"><div class="company-profile-head"><div><span class="eyebrow">${selected.universeTier} · ${esc(selected.securityCode)}</span><h2>${esc(selected.canonicalName)}</h2><p>${esc(selected.aliases.join("、"))}</p></div><button class="text-button" data-entity-id="${selected.entityId}">${icon("panel-right-open")}主体档案</button></div><div class="company-profile-kpis"><div><strong>${dailyItems.reduce((sum, item) => sum + item.sourceRecordIds.length, 0)}</strong><span>本期公告</span></div><div><strong>${events.length}</strong><span>事件节点</span></div><div><strong>${reports.length}</strong><span>财务披露</span></div><div><strong>${watches.length}</strong><span>我的跟踪</span></div></div><div class="company-profile-section"><div class="panel-head"><h2>公司事件时间线</h2><span>点击查看证据与复核</span></div><div class="company-events">${timeline || emptyState("暂无事件")}</div></div></section></div>`;
}

function bindListedControls() {
  $$('[data-listed-filter]').forEach((control) => control.addEventListener(control.tagName === "INPUT" ? "input" : "change", () => {
    state.listedFilters[control.dataset.listedFilter] = control.value;
    renderListed();
    refreshIcons();
  }));
  $("#listedPeriod")?.addEventListener("change", (event) => {
    state.listedPeriod = event.target.value;
    renderListed();
    refreshIcons();
  });
}

const dealStageLabels = {
  planning: "筹划中", signed_or_approved: "已签署/获批", in_progress: "推进中",
  completed: "已完成", terminated: "已终止"
};

function renderDeals() {
  if (!state.maProjects || !state.preIpo) {
    $("#view-deals").innerHTML = emptyState("并购与融资数据加载失败");
    return;
  }
  const tabs = [
    ["projects", "并购项目", `${state.maProjects.projectCount}个项目`],
    ["timeline", "项目时间线", "逐项目查看"],
    ["preipo", "拟上市企业", `${state.preIpo.reserveTotalCount}家后备`],
    ["financing", "融资记录", `${state.preIpo.financingRecords.length}条已核验`]
  ];
  const tabBar = `<div class="workspace-tabs" role="tablist">${tabs.map(([value, label, sub]) => `<button class="${state.dealsTab === value ? "active" : ""}" data-deals-tab="${value}" role="tab" aria-selected="${state.dealsTab === value}"><strong>${label}</strong><span>${sub}</span></button>`).join("")}</div>`;
  const views = { projects: renderMaProjects, timeline: renderMaTimeline, preipo: renderPreIpo, financing: renderFinancing };
  $("#view-deals").innerHTML = `${pageHeading("DEALS & CAPITAL", "并购与融资工作台", "并购按项目持续更新，拟上市企业按层级跟踪，融资记录只收录可回源事实。", `并购 ${state.maProjects.projectCount} 项<br>上市后备 ${state.preIpo.reserveTotalCount} 家`)}${tabBar}${views[state.dealsTab]()}`;
  bindDealsInputs();
}

function dealKpis() {
  const data = state.maProjects;
  return `<div class="kpi-grid deals-kpis"><div class="kpi"><span class="kpi-top"><span>并购项目池</span>${icon("git-merge")}</span><strong class="kpi-value">${data.projectCount}<span class="kpi-delta">一项目一时间线</span></strong></div><div class="kpi"><span class="kpi-top"><span>筹划与推进</span>${icon("activity")}</span><strong class="kpi-value">${data.stageCounts.planning + data.stageCounts.in_progress}<span class="kpi-delta">持续观察</span></strong></div><div class="kpi"><span class="kpi-top"><span>已完成</span>${icon("circle-check-big")}</span><strong class="kpi-value">${data.stageCounts.completed}<span class="kpi-delta">保留历史</span></strong></div><div class="kpi"><span class="kpi-top"><span>官方来源</span>${icon("shield-check")}</span><strong class="kpi-value">${data.officialSourceProjectCount}<span class="kpi-delta">逐条已回源</span></strong></div><div class="kpi"><span class="kpi-top"><span>待补来源</span>${icon("file-warning")}</span><strong class="kpi-value">${data.sourceBackfillCount}<span class="kpi-delta">不冒充核验</span></strong></div></div>`;
}

function filteredMaProjects() {
  const query = state.dealsQuery.trim().toLowerCase();
  return state.maProjects.projects.filter((item) => (state.dealsStage === "all" || item.stage === state.dealsStage) && (!query || `${item.title}${item.partiesText}${item.industry}${item.direction}`.toLowerCase().includes(query)));
}

function maToolbar() {
  return `<div class="toolbar deals-toolbar"><label class="search-field">${icon("search")}<input id="dealsQuery" type="search" value="${esc(state.dealsQuery)}" placeholder="搜索项目、交易方或行业"></label><select id="dealsStage">${option("all", "全部阶段", state.dealsStage)}${Object.entries(dealStageLabels).map(([value, label]) => option(value, label, state.dealsStage)).join("")}</select></div>`;
}

function renderMaProjects() {
  const projects = filteredMaProjects();
  const rows = projects.map((item) => `<article class="ma-project-row" data-ma-project="${item.maProjectId}"><div class="ma-stage stage-${item.stage}"><strong>${dealStageLabels[item.stage]}</strong><span>${esc(item.statusText)}</span></div><div class="ma-project-main"><div class="signal-meta"><span>${esc(item.dimension)}</span><span>${esc(item.industry)}</span>${item.sourceStatus === "official" ? '<span class="badge green">官方已回源</span>' : '<span class="badge amber">待补来源</span>'}</div><h3>${esc(item.title)}</h3><p>${esc(item.significance)}</p><small>${esc(item.partiesText)}</small></div><div class="ma-next"><span>下一节点</span><strong>${esc(item.nextAction)}</strong><em>${item.milestones.length}个里程碑 ${icon("chevron-right")}</em></div></article>`).join("");
  return `${dealKpis()}${maToolbar()}<section class="panel ma-project-panel"><div class="panel-head"><h2>项目池</h2><span>当前筛选 ${projects.length} 项</span></div><div class="ma-project-list">${rows || emptyState("当前筛选无项目")}</div></section>`;
}

function renderMaTimeline() {
  const projects = filteredMaProjects();
  const cards = projects.map((item) => `<article class="ma-timeline-card" data-ma-project="${item.maProjectId}"><div class="ma-timeline-head"><div><span>${esc(item.dimension)} · ${esc(item.industry)}</span><h3>${esc(item.title)}</h3></div><strong>${dealStageLabels[item.stage]}</strong></div><div class="timeline">${item.milestones.map((milestone) => `<div class="timeline-item"><span>${esc(milestone.at)}</span><strong>${esc(milestone.label)}</strong></div>`).join("")}</div><div class="ma-timeline-foot"><span>${item.sourceStatus === "official" ? "官方来源已关联" : "历史项目待补官方来源"}</span><b>查看详情 ${icon("arrow-right")}</b></div></article>`).join("");
  return `${maToolbar()}<div class="source-caveat">${icon("info")}<span>时间线只追加里程碑，不为同一项目重复新建长文；待补来源项目保留 V1 历史线索标签。</span></div><div class="ma-timeline-grid">${cards || emptyState("当前筛选无项目")}</div>`;
}

function renderPreIpo() {
  const query = state.preIpoQuery.trim().toLowerCase();
  const profiles = state.preIpo.profiles.filter((item) => !query || `${item.name}${item.latestMilestone}${item.reserveTier}`.toLowerCase().includes(query));
  const rows = profiles.map((item) => { const listed = item.listingStage.startsWith("listed"); return `<tr data-preipo-enterprise="${item.enterpriseId}"><td>${item.reserveRank || "--"}</td><td class="event-cell"><strong>${esc(item.name)}</strong><span>${listed ? `已上市毕业 · ${esc(item.securityCode || "")}` : `${item.reserveTier}档上市后备`}</span></td><td>${listed ? '<span class="badge green">已上市</span>' : `<span class="badge blue">${esc(item.reserveTier)}档</span>`}</td><td>${esc(item.latestMilestone)}</td><td>${esc(item.latestMilestoneAt)}</td><td>${item.financingStatus === "ipo_completed" ? "IPO已完成" : item.financingStatus === "verified" ? "已核验融资" : "未披露"}</td></tr>`; }).join("");
  return `<div class="kpi-grid preipo-kpis"><div class="kpi"><span class="kpi-top"><span>全省上市后备</span>${icon("building-2")}</span><strong class="kpi-value">${state.preIpo.reserveTotalCount}<span class="kpi-delta">2026名录</span></strong></div><div class="kpi"><span class="kpi-top"><span>A档优先池</span>${icon("star")}</span><strong class="kpi-value">${state.preIpo.tierCounts.A}<span class="kpi-delta">已逐家建档</span></strong></div><div class="kpi"><span class="kpi-top"><span>B档</span>${icon("layers-2")}</span><strong class="kpi-value">${state.preIpo.tierCounts.B}</strong></div><div class="kpi"><span class="kpi-top"><span>C档</span>${icon("layers-3")}</span><strong class="kpi-value">${state.preIpo.tierCounts.C}</strong></div><div class="kpi"><span class="kpi-top"><span>上市毕业</span>${icon("graduation-cap")}</span><strong class="kpi-value">${state.preIpo.graduatedCount}</strong></div></div><div class="source-caveat verified">${icon("shield-check")}<span>530家总量来自2026年度省级上市后备企业名录；当前逐家建档覆盖A档80家，B/C档保留总量口径，未伪造明细。</span></div><div class="toolbar"><label class="search-field">${icon("search")}<input id="preIpoQuery" type="search" value="${esc(state.preIpoQuery)}" placeholder="搜索A档企业或里程碑"></label></div><div class="data-table-wrap preipo-table"><table class="data-table"><thead><tr><th>名次</th><th>企业</th><th>状态</th><th>最新进展</th><th>日期</th><th>融资</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderFinancing() {
  const rows = state.preIpo.financingRecords.map((item) => { const company = state.preIpo.profiles.find((profile) => profile.enterpriseId === item.enterpriseId); return `<article class="financing-row"><div><span>${dateLabel(item.announcedAt)}</span><strong>${esc(item.round)}</strong></div><div><h3>${esc(company?.name || item.enterpriseId)}</h3><p>${esc(item.investors.join("、"))}</p></div><strong>${esc(item.amountText)}</strong><a href="${esc(item.sourceUrl)}" target="_blank" rel="noreferrer">官方投资人披露 ${icon("external-link")}</a></article>`; }).join("");
  return `<div class="source-caveat verified">${icon("badge-check")}<span>融资金额、轮次和投资方必须有可访问来源；未核验的传闻不进入本表。</span></div><section class="panel financing-panel"><div class="panel-head"><h2>已核验融资记录</h2><span>${state.preIpo.financingRecords.length}条</span></div>${rows || emptyState("暂无已核验融资记录")}</section>`;
}

function bindDealsInputs() {
  $("#dealsQuery")?.addEventListener("input", (event) => { state.dealsQuery = event.target.value; state.dealsTab === "timeline" ? renderMaTimelineIntoView() : renderDeals(); });
  $("#dealsStage")?.addEventListener("change", (event) => { state.dealsStage = event.target.value; renderDeals(); refreshIcons(); });
  $("#preIpoQuery")?.addEventListener("input", (event) => { state.preIpoQuery = event.target.value; renderDeals(); refreshIcons(); $("#preIpoQuery")?.focus(); });
}

function renderMaTimelineIntoView() { renderDeals(); refreshIcons(); $("#dealsQuery")?.focus(); }

function openMaProject(projectId) {
  const item = state.maProjects.projects.find((project) => project.maProjectId === projectId);
  if (!item) return;
  $("#drawerEyebrow").textContent = `${dealStageLabels[item.stage]} · ${item.industry}`;
  $("#drawerTitle").textContent = item.title;
  $("#drawerWatch").style.display = "none";
  const sources = item.sourceRecords.map((source, index) => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer"><span>${String(index + 1).padStart(2, "0")}</span><strong>${esc(source.title)}</strong>${icon("external-link")}</a>`).join("");
  $("#drawerBody").innerHTML = `<section class="detail-section"><div class="signal-meta"><span class="badge ${item.sourceStatus === "official" ? "green" : "amber"}">${item.sourceStatus === "official" ? "官方已回源" : "待补官方来源"}</span><span>${esc(item.dimension)}</span><span>${esc(item.amountText)}</span></div><p class="detail-summary">${esc(item.significance)}</p></section><section class="detail-section"><h3>下一步观察</h3><div class="next-action">${esc(item.nextAction)}</div></section><section class="detail-section"><h3>项目时间线</h3><div class="timeline">${item.milestones.map((milestone) => `<div class="timeline-item"><span>${esc(milestone.at)}</span><strong>${esc(milestone.label)}</strong></div>`).join("")}</div></section><section class="detail-section"><h3>来源与证据</h3>${sources ? `<div class="source-link-list">${sources}</div>` : `<div class="source-caveat">历史线索尚未逐条补齐官方公告，不据此输出新增结论。</div>`}</section>`;
  document.body.classList.add("drawer-open"); $("#detailDrawer").setAttribute("aria-hidden", "false"); refreshIcons();
}

function openPreIpo(enterpriseId) {
  const item = state.preIpo.profiles.find((profile) => profile.enterpriseId === enterpriseId);
  if (!item) return;
  const listed = item.listingStage.startsWith("listed");
  $("#drawerEyebrow").textContent = listed ? `已上市毕业 · ${item.securityCode || ""}` : `${item.reserveTier}档上市后备 · 第${item.reserveRank}名`;
  $("#drawerTitle").textContent = item.name; $("#drawerWatch").style.display = "none";
  $("#drawerBody").innerHTML = `<section class="detail-section"><div class="signal-meta"><span class="badge ${listed ? "green" : "blue"}">${listed ? "已上市" : `${item.reserveTier}档`}</span><span>${esc(item.securityCode || item.financingStatus)}</span></div><p class="detail-summary">${esc(item.latestMilestone)}</p></section><section class="detail-section"><h3>进展时间线</h3><div class="timeline">${item.milestones.map((milestone) => `<div class="timeline-item"><span>${esc(milestone.at)}</span><strong>${esc(milestone.label)}</strong></div>`).join("")}</div></section><section class="detail-section"><h3>来源</h3><div class="source-link-list">${item.milestones.map((milestone, index) => `<a href="${esc(milestone.sourceUrl)}" target="_blank" rel="noreferrer"><span>${String(index + 1).padStart(2, "0")}</span><strong>${esc(milestone.label)}</strong>${icon("external-link")}</a>`).join("")}</div></section>`;
  document.body.classList.add("drawer-open"); $("#detailDrawer").setAttribute("aria-hidden", "false"); refreshIcons();
}

function renderTender() {
  const monitor = state.data.tenderMonitor;
  const activeEvents = monitor.activeOpportunityEventIds.map(eventById).filter(Boolean);
  const runtimeActive = state.tenderRuntime?.activeOpportunities || [];
  const activeCount = activeEvents.length + runtimeActive.length;
  const tabs = [
    ["opportunities", "有效机会", `${activeCount}个可响应`],
    ["monitor", "扫描运行", `${monitor.scanIntervalMinutes}分钟目标`],
    ["history", "历史与漏检", `${monitor.projects.filter((item) => item.missReview).length + monitor.findings.filter((item) => item.alertStatus === "miss_review").length}项复盘`],
    ["sources", "官方来源", `${state.tenderRegistry?.sources.length || 0}个入口`]
  ];
  const tabBar = `<div class="workspace-tabs" role="tablist">${tabs.map(([value, label, sub]) => `<button class="${state.tenderTab === value ? "active" : ""}" data-tender-tab="${value}" role="tab" aria-selected="${state.tenderTab === value}"><strong>${label}</strong><span>${sub}</span></button>`).join("")}</div>`;
  const schedulerLabel = monitor.schedulerEnabled ? "自动扫描运行中" : state.tenderRuntime ? "扫描器已实跑·调度待启用" : "自动调度待启用";
  const content = state.tenderTab === "monitor" ? renderTenderMonitor() : state.tenderTab === "history" ? renderTenderHistory() : state.tenderTab === "sources" ? renderTenderSources() : renderTenderOpportunities(activeEvents, runtimeActive);
  $("#view-tender").innerHTML = `${pageHeading("TENDER WATCH", "金融招投标机会", "只在公告阶段且截止仍有效时提醒；结果、过期和非证券采购分流处理。", `当前有效 ${activeCount} 个<br>${schedulerLabel}`)}${tabBar}${content}`;
}

function privateFundKpis() {
  const item = state.privateFund;
  const summary = item.summary;
  const annual = state.privateWorkspace?.summary;
  return `<div class="kpi-grid private-kpis"><div class="kpi"><span class="kpi-top"><span>重要观察管理人</span>${icon("building-2")}</span><strong class="kpi-value">${summary.managerCount}<span class="kpi-delta">属地${summary.territorialManagerCount} + 强关联${summary.relatedManagerCount}</span></strong></div><div class="kpi"><span class="kpi-top"><span>2026备案产品</span>${icon("files")}</span><strong class="kpi-value">${annual?.productCount ?? summary.ytdProductCount}<span class="kpi-delta">AMAC公示</span></strong></div><div class="kpi"><span class="kpi-top"><span>年内备案管理人</span>${icon("briefcase-business")}</span><strong class="kpi-value">${annual?.managerCount ?? "--"}<span class="kpi-delta">有新产品</span></strong></div><div class="kpi"><span class="kpi-top"><span>前20人员覆盖</span>${icon("user-check")}</span><strong class="kpi-value">${summary.personnelCoveredCount}/${summary.topManagerCount}<span class="kpi-delta">详情已回源</span></strong></div><div class="kpi"><span class="kpi-top"><span>公开托管机构</span>${icon("network")}</span><strong class="kpi-value">${annual?.custodianCount ?? item.custodianSummary.length}<span class="kpi-delta">年内产品口径</span></strong></div></div>`;
}

function renderPrivate() {
  const data = state.privateFund;
  if (!data) {
    $("#view-private").innerHTML = emptyState("证券私募快照加载失败");
    return;
  }
  const tabs = [
    ["filings", "年度备案", `${state.privateWorkspace?.summary.productCount || data.summary.ytdProductCount}只产品`],
    ["ranking", "活跃前20", "公式可解释"],
    ["people", "人员跟踪", `${data.summary.personnelCoveredCount}/${data.summary.topManagerCount}覆盖`],
    ["relations", "关系与异动", `${data.custodianSummary.length}家托管人`]
  ];
  const tabBar = `<div class="workspace-tabs" role="tablist">${tabs.map(([value, label, sub]) => `<button class="${state.privateTab === value ? "active" : ""}" data-private-tab="${value}" role="tab" aria-selected="${state.privateTab === value}"><strong>${label}</strong><span>${sub}</span></button>`).join("")}</div>`;
  const views = { filings: renderPrivateFilings, ranking: renderPrivateRanking, people: renderPrivatePeople, relations: renderPrivateRelations };
  $("#view-private").innerHTML = `${pageHeading("PRIVATE FUND INTELLIGENCE", "证券私募情报台", "全年备案按季度查看，活跃度、人员和公开托管关系保持同一管理人口径。", `年度数据至 ${state.privateWorkspace?.asOf || data.sourceReportDate}<br>AMAC详情 ${data.summary.personnelCoveredCount}/${data.summary.topManagerCount}`)}${tabBar}${privateFundKpis()}${views[state.privateTab]()}`;
}

function renderPrivateFilings() {
  const workspace = state.privateWorkspace;
  if (!workspace) return emptyState("年度备案数据加载失败");
  const summary = workspace.summary;
  const maxMonth = Math.max(...workspace.monthlySeries.map((item) => item.count), 1);
  const monthBars = workspace.monthlySeries.map((item) => `<div class="private-month"><span>${item.month}月</span><i><b style="height:${Math.max(item.count / maxMonth * 100, item.count ? 12 : 0)}%"></b></i><strong>${item.count}</strong></div>`).join("");
  const leaders = `<div class="private-summary-leaders"><div><span>备案最多管理人</span><strong>${esc(summary.topManager?.name || "--")}</strong><em>${summary.topManager?.count || 0}只</em></div><div><span>备案最多托管人</span><strong>${esc(summary.topCustodian?.name || "--")}</strong><em>${summary.topCustodian?.count || 0}只</em></div><div><span>最近备案日期</span><strong>${esc(summary.latestFilingDate || "--")}</strong><em>${summary.activeQuarterCount}个季度有备案</em></div></div>`;
  const quarters = workspace.quarters.map(privateQuarterSection).join("");
  return `<div class="private-context"><span>${icon("calendar-range")}2026年度口径</span><strong>${summary.productCount}只产品 · ${summary.managerCount}家管理人</strong><p>按协会备案日归入季度；季度数量可相加，管理人和托管机构跨季度去重后进入年度汇总。</p></div><section class="panel private-year-summary"><div class="panel-head"><h2>年度备案节奏</h2><span>截至 ${workspace.asOf}</span></div><div class="private-year-body"><div class="private-month-chart">${monthBars}</div>${leaders}</div></section><div class="private-quarter-list">${quarters}</div>`;
}

function privateQuarterSection(quarter) {
  const open = state.privateOpenQuarters.has(quarter.quarter);
  const products = quarter.products.map((item) => `<article class="private-quarter-product"><div><strong>${dateLabel(item.filingDate)}</strong><span>${esc(item.fundNo)}</span></div><div><h3>${esc(item.fundName)}</h3><p>${esc(item.managerName)}</p></div><div><span>托管人</span><strong>${esc(item.custodian)}</strong></div><a href="${esc(item.sourceUrl)}" target="_blank" rel="noreferrer" title="查看AMAC公示" aria-label="查看AMAC公示">${icon("external-link")}</a></article>`).join("");
  return `<section class="private-quarter ${open ? "open" : ""}"><button class="private-quarter-head" data-private-quarter="${quarter.quarter}" aria-expanded="${open}"><span class="private-quarter-code">${quarter.quarter}</span><span><strong>${quarter.label}</strong><small>${quarter.dateRange}</small></span><span class="private-quarter-metrics"><b>${quarter.productCount}</b>只产品 · ${quarter.managerCount}家管理人 · ${quarter.custodianCount}家托管人</span>${icon(open ? "chevron-up" : "chevron-down")}</button>${open ? `<div class="private-quarter-products">${products || emptyState("本季度暂无备案产品")}</div>` : ""}</section>`;
}

function renderPrivateRanking() {
  const data = state.privateFund;
  const rows = data.topManagers.map((item) => `<tr data-private-manager="${esc(item.registerNo)}"><td><strong class="rank-number">${String(item.rank).padStart(2, "0")}</strong></td><td class="event-cell"><strong>${esc(item.managerName)}</strong><span>${esc(item.universeTier)} · ${esc(item.registerNo)} · ${esc(item.officeCity || item.officeProvince)}</span></td><td><strong>${item.activityScore}</strong></td><td>${item.scoreEvidence.totalProductCount}</td><td>${item.scoreEvidence.ytdNewProductCount}</td><td>${item.scoreEvidence.latestFilingDate || "--"}</td><td>${esc(item.scaleRange || "未披露")}</td><td>${item.employeeCount ?? "--"} / ${item.qualifiedCount ?? "--"}</td></tr>`).join("");
  return `<div class="private-context"><span>${icon("calculator")}排序口径</span><strong>${esc(data.rankingMethod.formula)}</strong><p>${esc(data.rankingMethod.purpose)}</p></div><div class="data-table-wrap private-ranking-table"><table class="data-table"><thead><tr><th>排名</th><th>管理人</th><th>活跃分</th><th>存量产品</th><th>年内备案</th><th>最近备案</th><th>规模区间</th><th>全职/从业</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderPrivatePeople() {
  const data = state.privateFund;
  const rows = data.topManagers.map((item) => {
    const backgrounds = [...new Set(item.workHistory.map((row) => row.company).filter((company) => company && company !== item.managerName && !["无", "自由职业"].includes(company)))].slice(0, 2);
    const brief = [`实控人 ${item.actualController || "未披露"}`, backgrounds.length ? `外部履历 ${backgrounds.join("、")}` : "暂无外部履历线索"].join(" · ");
    return `<article class="private-person-row" data-private-manager="${esc(item.registerNo)}"><div class="private-person-rank"><strong>${String(item.rank).padStart(2, "0")}</strong><span>${item.executives.length}名高管</span></div><div><h3>${esc(item.managerName)}</h3><p>${item.executives.map((person) => `${esc(person.name)} · ${esc(person.role)}`).join("　")}</p><small>${esc(brief)}</small></div><div><strong>${item.employeeCount ?? "--"}名全职</strong><span>${item.qualifiedCount ?? "--"}名基金从业</span><em>${esc(item.scaleRange || "规模未披露")}</em></div></article>`;
  }).join("");
  return `<div class="scheduler-banner pending private-baseline">${icon("history")}<div><strong>人员首期基线已建立，暂不输出离任或跳槽结论</strong><p>${esc(data.personnelBaselineNote)}</p></div><span>baseline</span></div><section class="panel private-section"><div class="panel-head"><h2>前20管理人人员档案</h2><span>点击查看履历和AMAC原文</span></div><div class="private-person-list">${rows}</div></section>`;
}

function renderPrivateRelations() {
  const data = state.privateFund;
  const max = Math.max(...data.custodianSummary.map((item) => item.productCount), 1);
  const custodians = data.custodianSummary.map((item) => `<div class="custodian-row"><strong>${esc(item.custodian)}</strong><span><i style="width:${item.productCount / max * 100}%"></i></span><b>${item.productCount}只</b></div>`).join("");
  const locations = data.locationObservations.slice(0, 12).map((item) => `<div class="location-row"><div><strong>${esc(item.managerName)}</strong><span>${esc(item.registerProvince)}注册 · ${esc(item.officeProvince)}办公</span></div><em>${item.direction === "office_in_shaanxi" ? "办公地在陕" : "注册地在陕"}</em></div>`).join("");
  const related = data.managerUniverse.filter((item) => item.universeTier === "PF2").map((item) => `<div class="location-row"><div><strong>${esc(item.managerName)}</strong><span>${esc(item.inclusionReason)}</span></div><em>强关联重要观察</em></div>`).join("");
  return `<section class="panel"><div class="panel-head"><h2>陕西强关联观察对象</h2><span>逐家人工准入 · 不与属地数量混算</span></div><div class="location-list">${related || emptyState("暂无强关联对象")}</div></section><div class="private-relation-grid"><section class="panel"><div class="panel-head"><h2>公开托管关系</h2><span>年内备案产品 · 不等同全部券商合作</span></div><div class="custodian-list">${custodians}</div></section><section class="panel"><div class="panel-head"><h2>注册地址与办公地异省</h2><span>观察项，不直接判断迁入迁出</span></div><div class="location-list">${locations}</div></section></div><section class="panel private-business-panel"><div class="panel-head"><h2>RM Dashboard 私募 PB 业务映射</h2><span>线索转业务的统一分类</span></div><div>${data.businessTaxonomy.map((item) => `<span>${esc(item.name)}</span>`).join("")}</div></section>`;
}

function openPrivateManager(registerNo) {
  const item = state.privateFund.topManagers.find((manager) => manager.registerNo === registerNo);
  if (!item) return;
  $("#drawerEyebrow").textContent = `活跃度第${item.rank} · ${item.registerNo}`;
  $("#drawerTitle").textContent = item.managerName;
  $("#drawerWatch").style.display = "none";
  const executives = item.executives.map((person) => `<div class="private-drawer-person"><strong>${esc(person.name)}</strong><span>${esc(person.role)}</span></div>`).join("");
  const histories = item.workHistory.map((row) => `<div class="timeline-item"><span>${esc(row.time)}</span><strong>${esc(row.company)} · ${esc(row.department)} · ${esc(row.role)}</strong></div>`).join("");
  const relation = item.universeTier === "PF2" ? `<p class="detail-summary"><strong>陕西强关联：</strong>${esc(item.inclusionReason)}</p>` : "";
  $("#drawerBody").innerHTML = `<section class="detail-section"><div class="signal-meta"><span class="badge green">活跃分 ${item.activityScore}</span><span class="badge blue">${esc(item.universeTier)}</span><span>${item.scoreEvidence.totalProductCount}只存量产品</span><span>${item.scoreEvidence.ytdNewProductCount}只年内备案</span></div><p class="detail-summary">${esc(item.teamSummary)}</p>${relation}</section><section class="detail-section"><h3>当前高管</h3><div class="private-drawer-people">${executives || emptyState("未提取到高管")}</div></section><section class="detail-section"><h3>公开履历</h3><div class="timeline">${histories || emptyState("未提取到履历")}</div></section><section class="detail-section"><h3>证据</h3><div class="source-link-list"><a href="${esc(item.detailUrl)}" target="_blank" rel="noreferrer"><span>01</span><strong>AMAC管理人详情页</strong>${icon("external-link")}</a></div></section>`;
  document.body.classList.add("drawer-open");
  $("#detailDrawer").setAttribute("aria-hidden", "false");
  refreshIcons();
}

function tenderKpis() {
  const monitor = state.data.tenderMonitor;
  const runtime = state.tenderRuntime;
  const missed = monitor.projects.filter((item) => item.missReview).length + monitor.findings.filter((item) => item.alertStatus === "miss_review").length;
  const excluded = monitor.findings.filter((item) => item.classification === "excluded").length;
  const latestRun = monitor.scanRuns.at(-1);
  const activeCount = runtime?.summary.activeOpportunityCount ?? monitor.activeOpportunityEventIds.length;
  const excludedCount = runtime?.summary.excludedCount ?? excluded;
  const latestAt = runtime?.generatedAt || latestRun.finishedAt;
  return `<div class="kpi-grid"><div class="kpi"><span class="kpi-top"><span>有效机会</span>${icon("bell-ring")}</span><strong class="kpi-value">${activeCount}<span class="kpi-delta">仍可响应</span></strong></div><div class="kpi"><span class="kpi-top"><span>扫描频率目标</span>${icon("refresh-cw")}</span><strong class="kpi-value">${monitor.scanIntervalMinutes}<span class="kpi-delta">分钟</span></strong></div><div class="kpi"><span class="kpi-top"><span>漏检复盘</span>${icon("history")}</span><strong class="kpi-value">${missed}<span class="kpi-delta">结果/过期</span></strong></div><div class="kpi"><span class="kpi-top"><span>适配排除</span>${icon("filter-x")}</span><strong class="kpi-value">${excludedCount}<span class="kpi-delta">保留审计</span></strong></div><div class="kpi"><span class="kpi-top"><span>最近运行</span>${icon("activity")}</span><strong class="kpi-value tender-run-time">${shortDateTime(latestAt)}<span class="kpi-delta">${runtime ? "实时扫描" : "V1导入"}</span></strong></div></div>`;
}

function renderTenderOpportunities(activeEvents, runtimeActive = []) {
  const eventRows = activeEvents.map((event) => {
    const signal = signalByEvent(event.eventId);
    return signalRow(signal);
  }).join("");
  const runtimeRows = runtimeActive.map((item) => `<article class="live-opportunity-row"><div class="live-opportunity-hours"><strong>${Math.max(0, item.remainingHours)}</strong><span>小时剩余</span></div><div><div class="signal-meta"><span class="badge red">即时机会</span><span>${esc(item.region)}</span><span>${dateLabel(item.publishedAt)}公告</span></div><h3>${esc(item.title)}</h3><p>${esc(item.purchaser)} · ${esc(item.category)}</p><small>${esc(item.contentExcerpt.slice(0, 220))}</small></div><a href="${esc(item.sourceUrl)}" target="_blank" rel="noreferrer">官方正文 ${icon("external-link")}</a></article>`).join("");
  const content = eventRows || runtimeRows ? `${eventRows}${runtimeRows}` : `<div class="tender-empty"><span class="tender-empty-icon">${icon("inbox")}</span><h2>当前没有仍可响应的证券类机会</h2><p>最新实跑未发现公告期有效且可确认证券公司可投的项目。页面不会用历史中标结果或普通IT采购填充这里。</p><div><span>${icon("check")}公告阶段</span><span>${icon("check")}截止有效</span><span>${icon("check")}资格适配</span><span>${icon("check")}官方正文</span></div></div>`;
  return `${tenderKpis()}<div class="tender-rule-strip"><strong>机会准入四条件</strong><span>公告阶段</span><span>截止时间明确且剩余小时大于0</span><span>证券公司资格适配</span><span>官方正文已回源</span></div><section class="panel tender-opportunity-panel"><div class="panel-head"><h2>即时机会区</h2><span>符合条件时不等待上午/盘后日报</span></div>${content}</section>`;
}

function renderTenderMonitor() {
  const monitor = state.data.tenderMonitor;
  const runtime = state.tenderRuntime;
  const runRows = monitor.scanRuns.map((run) => `<div class="scan-run-row"><span class="scan-status ${run.status === "PASS" ? "pass" : "review"}"></span><div><strong>${shortDateTime(run.finishedAt)} · ${run.runMode === "v1_manual_import" ? "V1人工运行导入" : "自动扫描"}</strong><p>${esc(run.note)}</p><small>${run.sourceScope.map(esc).join(" · ")}</small></div><div class="scan-run-metrics"><span><b>${run.candidateCount}</b>候选</span><span><b>${run.activeOpportunityCount}</b>机会</span><span><b>${run.resultFindingCount}</b>结果</span><span><b>${run.excludedCount}</b>排除</span></div><em>${run.status}</em></div>`).join("");
  const findingRows = monitor.findings.map((finding) => `<div class="finding-row ${finding.classification}"><div><div class="signal-meta"><span class="badge ${finding.classification === "excluded" ? "blue" : "amber"}">${finding.classification === "excluded" ? "已排除" : "待回源"}</span><span>${esc(finding.purchaser)}</span><span>${dateLabel(finding.discoveredAt)}发现</span></div><h3>${esc(finding.title)}</h3><p>${esc(finding.decision)}</p></div><div><strong>${finding.deadlineAt ? dateLabel(finding.deadlineAt) : "截止未知"}</strong><span>${esc(finding.nextAction)}</span></div></div>`).join("");
  const liveSummary = runtime ? `<div class="live-scan-summary"><div><span class="live-dot"></span><strong>官方接口实跑</strong><small>${shortDateTime(runtime.generatedAt)}</small></div><div><b>${runtime.summary.recordCount}</b><span>去重记录</span></div><div><b>${runtime.summary.newCount}</b><span>本轮新增</span></div><div><b>${runtime.summary.changedCount}</b><span>内容变化</span></div><div><b>${runtime.summary.sourcePass}/${runtime.sourceRuns.length}</b><span>来源通过</span></div><div><b>${runtime.summary.pendingCount}</b><span>待复核</span></div></div>` : "";
  return `${tenderKpis()}<div class="scheduler-banner ${monitor.schedulerEnabled ? "running" : "pending"}">${icon(monitor.schedulerEnabled ? "circle-play" : "circle-pause")}<div><strong>${monitor.schedulerEnabled ? "60分钟自动扫描已运行" : runtime ? "扫描器已实跑，60分钟系统调度尚未启用" : "60分钟自动调度尚未启用"}</strong><p>${monitor.schedulerEnabled ? "机会命中后立即生成提醒。" : runtime ? "官方全文检索、内容指纹、差异和分类已执行；仍需接入系统定时器。" : "当前仅展示V1运行导入结果。"}</p></div><span>${monitor.schedulerEnabled ? monitor.schedulerStatus : runtime ? "runner_ready" : monitor.schedulerStatus}</span></div>${liveSummary}<div class="tender-monitor-grid"><section class="panel"><div class="panel-head"><h2>运行记录</h2><span>开始、结束、候选与结果</span></div><div class="scan-run-list">${runRows}</div></section><section class="panel"><div class="panel-head"><h2>候选与排除</h2><span>不进入机会区</span></div><div class="finding-list">${findingRows}</div></section></div>`;
}

function renderTenderHistory() {
  const monitor = state.data.tenderMonitor;
  const projectRows = monitor.projects.map((project) => {
    const event = eventById(project.eventId);
    const entity = entityById(project.procurementEntityId);
    return `<article class="miss-review-row" data-event-id="${event.eventId}"><div class="miss-hours"><strong>${Math.abs(project.remainingHoursAtDiscovery)}</strong><span>小时后才发现</span></div><div><div class="signal-meta"><span class="badge red">漏检复盘</span><span>${esc(project.projectCode)}</span><span>${esc(entity.canonicalName)}</span></div><h3>${esc(event.title)}</h3><p>${esc(project.missReason)}</p><small>${esc(project.fitRationale)}</small></div><div><strong>${dateLabel(project.publishedAt)}公告</strong><span>${dateLabel(project.deadlineAt)}截止</span><em>${esc(project.firstDiscoveryStage)}</em></div></article>`;
  }).join("");
  const resultFindings = monitor.findings.filter((item) => item.alertStatus === "miss_review").map((finding) => `<article class="miss-review-row"><div class="miss-hours"><strong>结果</strong><span>阶段首次发现</span></div><div><div class="signal-meta"><span class="badge amber">正文待回源</span><span>${esc(finding.purchaser)}</span></div><h3>${esc(finding.title)}</h3><p>${esc(finding.decision)}</p><small>${esc(finding.nextAction)}</small></div><div><strong>${dateLabel(finding.publishedAt)}结果</strong><span>${dateLabel(finding.discoveredAt)}发现</span><em>discovery_only</em></div></article>`).join("");
  return `<div class="miss-review-list">${projectRows}${resultFindings || ""}</div>`;
}

function renderTenderSources() {
  const registry = state.tenderRegistry;
  if (!registry) return emptyState("来源注册表加载失败");
  const rows = registry.sources.map((source) => { const live = state.tenderRuntime?.sourceRuns.find((item) => item.sourceId === source.sourceId); const status = live?.status || source.status; return `<a class="tender-source-row" href="${esc(source.url)}" target="_blank" rel="noreferrer"><span class="source-authority ${source.authority}">${source.authority === "official" ? "官方" : "权威"}</span><div><strong>${esc(source.name)}</strong><p>${esc(source.adapter)} · ${source.stages.join(" / ")}</p></div><span>${source.scanIntervalMinutes}分钟</span><em class="${status === "PASS" ? "status-pass" : status.startsWith("FAIL") ? "status-fail" : ""}">${status}</em>${icon("external-link")}</a>`; }).join("");
  const sourcePass = state.tenderRuntime?.summary.sourcePass ?? 0;
  return `<div class="scheduler-banner ${registry.schedulerEnabled ? "running" : "pending"}">${icon("database")}<div><strong>${registry.schedulerEnabled ? `60分钟来源扫描已启用 · ${sourcePass}/${registry.sources.length}来源通过` : "来源注册表已建立，自动调度待启用"}</strong><p>${esc(registry.note)}</p></div><span>${registry.schedulerEnabled ? esc(registry.automationId || "running") : "not_enabled"}</span></div><section class="panel"><div class="panel-head"><h2>官方与权威来源</h2><span>${registry.sources.length}个 · ${registry.scanIntervalMinutes}分钟目标</span></div><div class="tender-source-list">${rows}</div></section><section class="panel keyword-panel"><div class="panel-head"><h2>组合检索词</h2><span>产品 × 服务 × 动作</span></div><div class="keyword-groups">${Object.entries(registry.keywordGroups).map(([key, values]) => `<div><strong>${key === "products" ? "产品" : key === "services" ? "服务" : "动作"}</strong><p>${values.map((value) => `<span>${esc(value)}</span>`).join("")}</p></div>`).join("")}</div></section>`;
}

function kpi(label, value, iconName, delta, view) {
  return `<button class="kpi" data-view="${view}"><span class="kpi-top"><span>${label}</span>${icon(iconName)}</span><strong class="kpi-value">${value}<span class="kpi-delta">${delta}</span></strong></button>`;
}

function deadlineRow(event) {
  const signal = signalByEvent(event.eventId);
  const lead = leadBySignal(signal?.signalId);
  return `<article class="deadline-row" data-event-id="${event.eventId}"><span class="days-left"><strong>${daysFromSnapshot(event.deadlineAt)}</strong><span>天</span></span><div><div class="signal-meta">${labels.channels[event.channel].name}<span>${dateLabel(event.deadlineAt)}</span></div><h3>${esc(event.title)}</h3><p>${esc(lead?.nextAction || "等待下一公开节点")}</p></div></article>`;
}

function watchCalendarItem(watch) {
  const event = eventById(watch.eventId);
  return `<div class="calendar-item" data-event-id="${event.eventId}"><span class="calendar-date">${dateLabel(watch.nextReviewAt)}</span><div><strong>${esc(entityById(watch.entityId).canonicalName)}</strong><p>${esc(watch.note || event.title)}</p></div>${watchBadge(watch.watchStatus)}</div>`;
}

function emptyState(text) {
  return `<div class="empty-row">${esc(text)}</div>`;
}

function createWatch(eventId) {
  const event = eventById(eventId);
  if (!event || watchByEvent(eventId)) return;
  const now = new Date();
  const review = new Date(now.getTime() + 7 * 86400000);
  state.watchItems.push({
    watchId: `watch-user-${eventId}`,
    eventId,
    entityId: event.primaryEntityId,
    watchStatus: "saved",
    priority: signalByEvent(eventId)?.priority || "medium",
    tags: [labels.channels[event.channel].name],
    business: event.business,
    note: "",
    nextReviewAt: review.toISOString(),
    createdAt: now.toISOString(),
    updatedAt: now.toISOString(),
    stateHistory: [{ status: "saved", at: now.toISOString() }]
  });
  persistWatchItems();
  showToast("已加入我的跟踪");
}

function removeWatch(eventId) {
  const index = state.watchItems.findIndex((item) => item.eventId === eventId);
  if (index < 0) return;
  state.watchItems.splice(index, 1);
  persistWatchItems();
  showToast("已取消跟踪");
}

function toggleWatch(eventId) {
  if (watchByEvent(eventId)) removeWatch(eventId);
  else createWatch(eventId);
  renderDashboard();
  if (state.view === "watch") renderWatch();
  if (state.view === "signals") renderSignals();
  if (state.view === "listed") renderListed();
  refreshIcons();
}

function renderWatch() {
  const filters = state.watchFilters;
  let items = [...state.watchItems];
  if (filters.channel !== "all") items = items.filter((item) => eventById(item.eventId).channel === filters.channel);
  if (filters.status !== "all") items = items.filter((item) => item.watchStatus === filters.status);
  if (filters.priority !== "all") items = items.filter((item) => item.priority === filters.priority);
  if (filters.query) {
    const query = filters.query.toLowerCase();
    items = items.filter((item) => {
      const event = eventById(item.eventId);
      const entity = entityById(item.entityId);
      return `${event.title}${entity.canonicalName}${item.note}${item.tags.join("")}`.toLowerCase().includes(query);
    });
  }
  items.sort((a, b) => {
    if (!a.nextReviewAt) return 1;
    if (!b.nextReviewAt) return -1;
    return new Date(a.nextReviewAt) - new Date(b.nextReviewAt);
  });
  const active = state.watchItems.filter((item) => !["resolved", "closed"].includes(item.watchStatus));
  const overdue = active.filter((item) => item.nextReviewAt && new Date(item.nextReviewAt) < new Date()).length;
  const following = active.filter((item) => item.watchStatus === "following").length;
  const waiting = active.filter((item) => item.watchStatus === "waiting").length;
  const rows = items.map(watchRow).join("");
  $("#view-watch").innerHTML = `${pageHeading("WATCHLIST", "我的跟踪", "收藏引用原事件，备注与事实分开保存。", `当前结果 ${items.length} 项<br>本机持久化`)}
    <div class="kpi-grid"><div class="kpi"><span class="kpi-top"><span>全部收藏</span>${icon("bookmark-check")}</span><strong class="kpi-value">${state.watchItems.length}</strong></div><div class="kpi"><span class="kpi-top"><span>活动跟踪</span>${icon("activity")}</span><strong class="kpi-value">${active.length}</strong></div><div class="kpi"><span class="kpi-top"><span>已到复核</span>${icon("alarm-clock")}</span><strong class="kpi-value">${overdue}</strong></div><div class="kpi"><span class="kpi-top"><span>跟进中</span>${icon("workflow")}</span><strong class="kpi-value">${following}</strong></div><div class="kpi"><span class="kpi-top"><span>等待节点</span>${icon("hourglass")}</span><strong class="kpi-value">${waiting}</strong></div></div>
    ${watchToolbar(filters)}
    <div class="watch-list">${rows || emptyState("当前筛选无跟踪事项")}</div>`;
  bindWatchToolbar();
}

function watchToolbar(filters) {
  const statuses = [["all", "全部状态"], ...Object.entries(labels.watchStatus)];
  return `<div class="toolbar" data-filter-kind="watch"><label class="search-field">${icon("search")}<input type="search" data-filter="query" value="${esc(filters.query)}" placeholder="搜索主体、事件、备注或标签"></label><select data-filter="channel">${option("all", "全部频道", filters.channel)}${Object.entries(labels.channels).map(([value, item]) => option(value, item.name, filters.channel)).join("")}</select><select data-filter="status">${statuses.map(([value, label]) => option(value, label, filters.status)).join("")}</select><select data-filter="priority">${option("all", "全部优先级", filters.priority)}${option("high", "高优先级", filters.priority)}${option("medium", "中优先级", filters.priority)}${option("low", "低优先级", filters.priority)}</select></div>`;
}

function bindWatchToolbar() {
  const root = $('[data-filter-kind="watch"]');
  $$('[data-filter]', root).forEach((control) => {
    control.addEventListener(control.tagName === "INPUT" ? "input" : "change", () => {
      state.watchFilters[control.dataset.filter] = control.value;
      renderWatch();
      refreshIcons();
    });
  });
}

function watchRow(watch) {
  const event = eventById(watch.eventId);
  const entity = entityById(watch.entityId);
  const overdue = watch.nextReviewAt && new Date(watch.nextReviewAt) < new Date() && !["resolved", "closed"].includes(watch.watchStatus);
  return `<article class="watch-row" data-event-id="${event.eventId}"><div class="watch-main"><div class="signal-meta">${watchBadge(watch.watchStatus)}<span>${labels.channels[event.channel].name}</span><span>${labels.business[watch.business] || watch.business}</span>${watch.tags.map((tag) => `<span>#${esc(tag)}</span>`).join("")}</div><h3>${esc(entity.canonicalName)}｜${esc(event.title)}</h3><p>${esc(event.summary)}</p></div><p class="watch-note">${esc(watch.note || "暂无工作备注")}</p><div class="watch-due ${overdue ? "overdue" : ""}"><span>下一复核</span><strong>${watch.nextReviewAt ? dateLabel(watch.nextReviewAt) : "未设置"}</strong></div><div class="watch-priority"><span>优先级</span><strong>${watch.priority === "high" ? "高" : watch.priority === "medium" ? "中" : "低"}</strong></div><button class="watch-remove" data-watch-remove="${event.eventId}" title="取消跟踪" aria-label="取消跟踪">${icon("bookmark-x")}</button></article>`;
}

function renderSignals() {
  let signals = [...state.data.signals];
  if (state.signalFilters.channel !== "all") signals = signals.filter((item) => eventById(item.eventId).channel === state.signalFilters.channel);
  if (state.signalFilters.status !== "all") signals = signals.filter((item) => item.signalStatus === state.signalFilters.status);
  if (state.signalFilters.query) {
    const query = state.signalFilters.query.toLowerCase();
    signals = signals.filter((item) => `${item.headline}${item.whyItMatters}${entityById(eventById(item.eventId).primaryEntityId).canonicalName}`.toLowerCase().includes(query));
  }
  signals.sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority] || new Date(eventById(b.eventId).publishedAt) - new Date(eventById(a.eventId).publishedAt));
  $("#view-signals").innerHTML = `${pageHeading("SIGNAL STREAM", "信号流", "一个事件只保留一个主信号。", `当前结果 ${signals.length} 条`)}${filterToolbar("signal", state.signalFilters)}<section class="panel"><div class="signal-list">${signals.length ? signals.map(signalRow).join("") : emptyState("当前筛选无数据")}</div></section>`;
  bindFilterToolbar("signal");
}

function filterToolbar(kind, filters) {
  const statusOptions = kind === "signal"
    ? [["all", "全部状态"], ["today_new", "今日新增"], ["action_window", "行动窗口"], ["risk", "风险"], ["data_update", "数据更新"], ["watch", "观察"], ["backfill", "回溯补录"], ["result_progress", "结果进展"]]
    : [["all", "全部状态"], ["action_window", "行动窗口"], ["progressing", "进展中"], ["risk", "风险"], ["watch", "观察"], ["completed", "已完成"]];
  return `<div class="toolbar" data-filter-kind="${kind}"><label class="search-field">${icon("search")}<input type="search" data-filter="query" value="${esc(filters.query)}" placeholder="搜索主体或事件"></label><select data-filter="channel">${option("all", "全部频道", filters.channel)}${Object.entries(labels.channels).map(([value, item]) => option(value, item.name, filters.channel)).join("")}</select><select data-filter="status">${statusOptions.map(([value, label]) => option(value, label, filters.status)).join("")}</select>${kind === "annual" ? `<select data-filter="business">${option("all", "全部业务", filters.business)}${Object.entries(labels.business).map(([value, label]) => option(value, label, filters.business)).join("")}</select><button class="export-button" id="exportCsv">${icon("download")}导出当前结果</button>` : ""}</div>`;
}

function option(value, label, current) {
  return `<option value="${value}" ${value === current ? "selected" : ""}>${label}</option>`;
}

function bindFilterToolbar(kind) {
  const root = $(`[data-filter-kind="${kind}"]`);
  if (!root) return;
  $$('[data-filter]', root).forEach((control) => {
    const eventName = control.tagName === "INPUT" ? "input" : "change";
    control.addEventListener(eventName, () => {
      state[`${kind}Filters`][control.dataset.filter] = control.value;
      kind === "signal" ? renderSignals() : renderAnnual();
      refreshIcons();
    });
  });
  $("#exportCsv", root)?.addEventListener("click", exportAnnualCsv);
}

function getAnnualEvents() {
  let events = [...state.data.events];
  const filters = state.annualFilters;
  if (filters.channel !== "all") events = events.filter((item) => item.channel === filters.channel);
  if (filters.status !== "all") events = events.filter((item) => item.eventStatus === filters.status);
  if (filters.business !== "all") events = events.filter((item) => item.business === filters.business);
  if (filters.query) {
    const query = filters.query.toLowerCase();
    events = events.filter((item) => `${item.title}${item.summary}${entityById(item.primaryEntityId).canonicalName}`.toLowerCase().includes(query));
  }
  return events.sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt));
}

function renderAnnual() {
  const events = getAnnualEvents();
  const intelligence = state.annualIntelligence;
  const entityCount = new Set(events.map((item) => item.primaryEntityId)).size;
  const activeCount = events.filter((item) => item.eventStatus === "action_window").length;
  const leadsCount = new Set(events.map((item) => signalByEvent(item.eventId)?.signalId).filter((id) => state.data.leads.some((lead) => lead.signalId === id))).size;
  const businessCounts = Object.entries(labels.business).map(([key, label]) => ({ key, label, count: events.filter((item) => item.business === key).length })).filter((item) => item.count).sort((a, b) => b.count - a.count);
  const max = Math.max(...businessCounts.map((item) => item.count), 1);
  const rows = events.map((event) => {
    const entity = entityById(event.primaryEntityId);
    return `<tr data-event-id="${event.eventId}"><td>${dateLabel(event.publishedAt)}</td><td><strong>${esc(entity.canonicalName)}</strong><br><span class="eyebrow">${esc(entity.securityCode || entity.entityType)}</span></td><td class="event-cell"><strong>${esc(event.title)}</strong><span>${esc(event.summary)}</span></td><td>${labels.channels[event.channel].name}</td><td>${labels.business[event.business] || event.business}</td><td>${badgeForStatus(event.eventStatus)}</td><td>${esc(event.metrics?.[0]?.value || "--")}</td><td>${event.deadlineAt ? dateLabel(event.deadlineAt) : "--"}</td><td>${qualityBadge(event.qualityStatus)}</td></tr>`;
  }).join("");
  const fullScope = intelligence ? `<div class="annual-scope"><div><span>上市日报</span><strong>${intelligence.metrics.listedDailyItems}</strong><em>有效事项</em></div><div><span>并购项目</span><strong>${intelligence.metrics.maProjects}</strong><em>${intelligence.metrics.maActiveProjects}项未完结</em></div><div><span>证券私募</span><strong>${intelligence.metrics.privateManagers}</strong><em>${intelligence.metrics.privateYtdProducts}只年内备案</em></div><div><span>上市后备</span><strong>${intelligence.metrics.reserveEnterprises}</strong><em>${intelligence.metrics.aTierProfiles}家A档建档</em></div><div><span>招投标扫描</span><strong>${intelligence.metrics.tenderScannedRecords}</strong><em>${intelligence.metrics.activeTenderOpportunities}项有效机会</em></div></div><div class="source-caveat verified annual-boundary">${icon("scale")}${esc(intelligence.dataBoundaries[0])} ${esc(intelligence.dataBoundaries[1])}</div>` : "";
  $("#view-annual").innerHTML = `${pageHeading("2026 EXPLORER", "年度数据", "先看各业务年度口径，再按唯一 eventId 下钻；不同口径不相加。", `当前筛选 ${events.length} 个事件<br>${entityCount} 个主体`)}${fullScope}${filterToolbar("annual", state.annualFilters)}
    <div class="kpi-grid"><div class="kpi"><span class="kpi-top"><span>唯一事件</span>${icon("hash")}</span><strong class="kpi-value">${events.length}</strong></div><div class="kpi"><span class="kpi-top"><span>覆盖主体</span>${icon("building-2")}</span><strong class="kpi-value">${entityCount}</strong></div><div class="kpi"><span class="kpi-top"><span>行动窗口</span>${icon("timer")}</span><strong class="kpi-value">${activeCount}</strong></div><div class="kpi"><span class="kpi-top"><span>已生成线索</span>${icon("briefcase-business")}</span><strong class="kpi-value">${leadsCount}</strong></div><div class="kpi"><span class="kpi-top"><span>已回源</span>${icon("badge-check")}</span><strong class="kpi-value">${events.filter((item) => item.qualityStatus === "verified").length}</strong></div></div>
    <div class="annual-summary"><section class="panel"><div class="panel-head"><h2>业务结构</h2><span>当前筛选口径</span></div><div class="business-bars">${businessCounts.map((item) => `<div class="business-row"><span>${item.label}</span><span class="business-track"><i style="width:${item.count / max * 100}%"></i></span><strong>${item.count}</strong></div>`).join("") || emptyState("当前筛选无数据")}</div></section><section class="panel"><div class="panel-head"><h2>质量结构</h2><span>字段可追溯</span></div><div class="business-bars"><div class="business-row"><span>已回源</span><span class="business-track"><i style="width:${events.length ? events.filter((item) => item.qualityStatus === "verified").length / events.length * 100 : 0}%"></i></span><strong>${events.filter((item) => item.qualityStatus === "verified").length}</strong></div><div class="business-row"><span>交叉核验</span><span class="business-track"><i style="width:${events.length ? events.filter((item) => item.qualityStatus === "cross_checked").length / events.length * 100 : 0}%;background:var(--amber)"></i></span><strong>${events.filter((item) => item.qualityStatus === "cross_checked").length}</strong></div></div></section></div>
    <div class="data-table-wrap"><table class="data-table"><thead><tr><th>日期</th><th>主体</th><th>事件</th><th>频道</th><th>业务</th><th>状态</th><th>关键数字</th><th>截止</th><th>质量</th></tr></thead><tbody>${rows || `<tr><td colspan="9" class="empty-row">当前筛选无数据</td></tr>`}</tbody></table></div>`;
  bindFilterToolbar("annual");
}

function renderLeads() {
  const columns = ["to_assess", "following", "waiting", "closed"];
  const board = columns.map((status) => {
    const leads = state.data.leads.filter((item) => item.leadStatus === status || (status === "following" && item.leadStatus === "to_contact"));
    return `<section class="lead-column"><div class="lead-column-head"><h2>${labels.leadStatus[status]}</h2><span>${leads.length}</span></div>${leads.map(leadCard).join("") || `<div class="empty-row">当前无项目</div>`}</section>`;
  }).join("");
  $("#view-leads").innerHTML = `${pageHeading("BUSINESS LEADS", "业务线索", "公开事实、业务依据和下一步动作分开记录。", `有效线索 ${state.data.leads.length} 条`)}<div class="lead-board">${board}</div>`;
}

function leadCard(lead) {
  const signal = signalById(lead.signalId);
  const event = eventById(signal.eventId);
  const entity = entityById(event.primaryEntityId);
  return `<article class="lead-card" data-event-id="${event.eventId}"><div class="signal-meta"><span class="badge blue">${labels.business[lead.businessType] || lead.businessType}</span><span>${lead.confidence === "high" ? "高置信" : "中置信"}</span></div><h3>${esc(entity.canonicalName)}｜${esc(lead.opportunityType)}</h3><p>${esc(lead.nextAction)}</p><div class="lead-due"><span>${labels.leadStatus[lead.leadStatus]}</span><strong>${dateLabel(lead.dueAt)}</strong></div></article>`;
}

function renderEntities() {
  if (state.entityTab === "relationships") { renderRelationships(); return; }
  const query = state.entityQuery.toLowerCase();
  const entities = state.data.entities.filter((item) => `${item.canonicalName}${item.aliases.join("")}${item.securityCode || ""}`.toLowerCase().includes(query));
  const cards = entities.map((entity) => {
    const events = state.data.events.filter((item) => item.primaryEntityId === entity.entityId);
    const actionCount = events.filter((item) => item.eventStatus === "action_window").length;
    const latest = [...events].sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt))[0];
    return `<button class="entity-card" data-entity-id="${entity.entityId}"><div class="entity-top"><div><h3>${esc(entity.canonicalName)}</h3><div class="entity-code">${esc(entity.securityCode || entity.entityType)} · ${esc(entity.region)}</div></div>${entity.universeTier ? `<span class="badge blue">${entity.universeTier}</span>` : badgeForStatus(entity.status === "cancelled" ? "completed" : "active")}</div><div class="entity-stats"><div><strong>${events.length}</strong><span>年内事件</span></div><div><strong>${actionCount}</strong><span>行动中</span></div><div><strong>${new Set(events.map((item) => item.channel)).size}</strong><span>关联频道</span></div></div><div class="entity-latest">${esc(latest?.title || "暂无事件")}</div></button>`;
  }).join("");
  $("#view-entities").innerHTML = `${pageHeading("ENTITY & RELATION", "主体关系", "主体目录与证据关系使用同一身份，不靠页面文字临时拼接。", `统一节点 ${state.relationships?.summary.nodeCount || entities.length} 个`)}${entityTabs()}<div class="toolbar"><label class="search-field">${icon("search")}<input id="entitySearch" type="search" value="${esc(state.entityQuery)}" placeholder="搜索主体、简称或证券代码"></label></div><div class="entity-grid">${cards || emptyState("当前筛选无主体")}</div>`;
  $("#entitySearch")?.addEventListener("input", (event) => { state.entityQuery = event.target.value; renderEntities(); refreshIcons(); });
}

function entityTabs() {
  const tabs = [["directory", "主体目录", `${state.data.entities.length}个核心主体`], ["relationships", "证据关系", `${state.relationships?.summary.edgeCount || 0}条关系边`]];
  return `<div class="workspace-tabs entity-tabs" role="tablist">${tabs.map(([value, label, sub]) => `<button class="${state.entityTab === value ? "active" : ""}" data-entity-tab="${value}" role="tab"><strong>${label}</strong><span>${sub}</span></button>`).join("")}</div>`;
}

function renderRelationships() {
  const data = state.relationships;
  if (!data) { $("#view-entities").innerHTML = emptyState("关系数据加载失败"); return; }
  const nodeMap = new Map(data.nodes.map((item) => [item.nodeId, item]));
  const relationLabels = { has_event: "关联事件", executive: "任职高管", shareholder_of: "股东", manages: "管理产品", custodied_by: "产品托管", linked_ma_project: "关联并购", invested_in: "投资关系" };
  const types = Object.keys(data.summary.relationTypeCounts);
  const edges = data.edges.filter((item) => state.relationType === "all" || item.relationType === state.relationType);
  const rows = edges.map((edge) => { const source = nodeMap.get(edge.sourceNodeId); const target = nodeMap.get(edge.targetNodeId); return `<tr><td class="event-cell"><strong>${esc(source?.name || edge.sourceNodeId)}</strong><span>${esc(source?.nodeType || "")}</span></td><td><span class="relation-arrow">${icon("arrow-right")}${esc(relationLabels[edge.relationType] || edge.relationType)}</span></td><td class="event-cell"><strong>${esc(target?.name || edge.targetNodeId)}</strong><span>${esc(target?.nodeType || "")}</span></td><td>${esc(edge.at || "--")}</td><td>${edge.sourceUrl ? `<a class="evidence-link" href="${esc(edge.sourceUrl)}" target="_blank" rel="noreferrer">${esc(edge.evidenceType)} ${icon("external-link")}</a>` : esc(edge.evidenceType)}</td></tr>`; }).join("");
  const relationKpis = [["统一节点", data.summary.nodeCount, "waypoints"], ["证据关系", data.summary.edgeCount, "share-2"], ["主体事件", data.summary.relationTypeCounts.has_event || 0, "newspaper"], ["人员与股东", (data.summary.relationTypeCounts.executive || 0) + (data.summary.relationTypeCounts.shareholder_of || 0), "users"], ["跨频道关系", (data.summary.relationTypeCounts.linked_ma_project || 0) + (data.summary.relationTypeCounts.invested_in || 0), "git-branch"]];
  $("#view-entities").innerHTML = `${pageHeading("ENTITY & RELATION", "主体关系", "每条关系边都有类型、数据时点和证据口径。", `节点 ${data.summary.nodeCount} 个<br>关系 ${data.summary.edgeCount} 条`)}${entityTabs()}<div class="kpi-grid relation-kpis">${relationKpis.map(([label, value, iconName]) => `<div class="kpi"><span class="kpi-top"><span>${label}</span>${icon(iconName)}</span><strong class="kpi-value">${value}</strong></div>`).join("")}</div><div class="toolbar"><select id="relationType">${option("all", "全部关系", state.relationType)}${types.map((type) => option(type, relationLabels[type] || type, state.relationType)).join("")}</select></div><div class="data-table-wrap relation-table"><table class="data-table"><thead><tr><th>起点</th><th>关系</th><th>终点</th><th>日期</th><th>证据</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  $("#relationType")?.addEventListener("change", (event) => { state.relationType = event.target.value; renderRelationships(); refreshIcons(); });
}

function renderQuality() {
  const sourceRows = [
    ["上市公司", "巨潮资讯、上海证券交易所、深圳证券交易所、北交所及港交所披露易"],
    ["证券私募", "中国证券投资基金业协会公开登记与备案信息"],
    ["并购融资与国企", "公司公告、政府部门、产权交易平台及企业官网"],
    ["金融招投标", "政府采购、公共资源交易与官方招标公告平台"],
  ].map(([name, description]) => `<div class="provider-row"><div><strong>${name}</strong><p>${description}</p></div><strong class="status-pass">公开来源</strong></div>`).join("");
  const coverageRows = [
    ["上市公司", `${state.listedUniverse?.counts.total ?? 0}家`, "按当前有效观察名单更新"],
    ["证券私募", `${state.privateFund?.summary.observationManagerCount ?? 0}家`, `年内${state.privateFund?.summary.ytdProductCount ?? 0}只产品备案`],
    ["并购与融资", `${state.maProjects?.projectCount ?? 0}项`, "按公开披露的交易阶段跟踪"],
    ["上市后备", `${state.preIpo?.reserveTotalCount ?? 0}家`, "以陕西省公开后备名单为准"],
  ].map(([name, value, note]) => `<div class="backfill-item"><div><span>${name}</span><strong>${value}</strong><p>${note}</p></div></div>`).join("");
  $("#view-quality").innerHTML = `${pageHeading("数据说明", "信息来源与覆盖口径", "本页所有内容均根据公开披露信息整理。", `更新至 ${state.listedWorkspace?.deepRead?.latestReportDate || "--"}`)}<div class="quality-grid"><section class="panel"><div class="panel-head"><h2>主要信息来源</h2><span>以公告原文为准</span></div><div class="provider-list">${sourceRows}</div></section><section class="panel"><div class="panel-head"><h2>当前覆盖</h2><span>持续更新</span></div><div class="backfill-grid">${coverageRows}</div></section></div><div class="audit-note">${icon("info")}<div><strong>说明</strong><br>本页用于公开信息整理与跟踪，不构成投资建议。公司公告、产品备案、项目阶段和人员信息均可能发生变化，重要决策请以相关机构最新公开披露为准。</div></div>`;
}

function watchEditor(event) {
  const watch = watchByEvent(event.eventId);
  if (!watch) return `<section class="detail-section"><h3>我的跟踪</h3><div class="watch-empty-action"><span>保存该事件，后续进展继续引用同一事件。</span><button class="text-button primary" data-watch-add="${event.eventId}">${icon("bookmark-plus")}加入跟踪</button></div></section>`;
  const statusOptions = Object.entries(labels.watchStatus).map(([value, label]) => option(value, label, watch.watchStatus)).join("");
  return `<section class="detail-section"><h3>我的跟踪</h3><div class="watch-editor"><div class="watch-editor-head"><strong>${watchBadge(watch.watchStatus)} 已保存于本机</strong><span>更新于 ${shortDateTime(watch.updatedAt)}</span></div><div class="watch-form-grid"><div class="watch-field"><label for="watchStatus">跟踪状态</label><select id="watchStatus">${statusOptions}</select></div><div class="watch-field"><label for="watchPriority">优先级</label><select id="watchPriority">${option("high", "高", watch.priority)}${option("medium", "中", watch.priority)}${option("low", "低", watch.priority)}</select></div><div class="watch-field"><label for="watchReviewAt">下一复核时间</label><input id="watchReviewAt" type="datetime-local" value="${toDateTimeInput(watch.nextReviewAt)}"></div><div class="watch-field"><label for="watchTags">标签（逗号分隔）</label><input id="watchTags" value="${esc(watch.tags.join("，"))}"></div><div class="watch-field full"><label for="watchNote">工作备注</label><textarea id="watchNote" placeholder="只记录工作备注，不改写事件事实">${esc(watch.note)}</textarea></div></div><div class="watch-form-actions"><button class="text-button danger" data-watch-remove="${event.eventId}">${icon("bookmark-x")}取消跟踪</button><button class="text-button primary" data-watch-save="${event.eventId}">${icon("save")}保存修改</button></div></div></section>`;
}

function saveWatchEditor(eventId) {
  const watch = watchByEvent(eventId);
  if (!watch) return;
  const nextStatus = $("#watchStatus").value;
  const nextReviewValue = $("#watchReviewAt").value;
  if (!["resolved", "closed"].includes(nextStatus) && !nextReviewValue) {
    showToast("活动跟踪必须设置下一复核时间");
    return;
  }
  const now = new Date().toISOString();
  if (nextStatus !== watch.watchStatus) watch.stateHistory.push({ status: nextStatus, at: now });
  watch.watchStatus = nextStatus;
  watch.priority = $("#watchPriority").value;
  watch.nextReviewAt = nextReviewValue ? new Date(nextReviewValue).toISOString() : null;
  watch.tags = [...new Set($("#watchTags").value.split(/[，,]/).map((item) => item.trim()).filter(Boolean))];
  watch.note = $("#watchNote").value.trim();
  watch.updatedAt = now;
  persistWatchItems();
  renderDashboard();
  if (state.view === "watch") renderWatch();
  if (state.view === "listed") renderListed();
  openEvent(eventId);
  showToast("跟踪信息已保存");
}

function openEvent(eventId) {
  const event = eventById(eventId);
  if (!event) return;
  const entity = entityById(event.primaryEntityId);
  const signal = signalByEvent(event.eventId);
  const lead = leadBySignal(signal?.signalId);
  const sources = event.sourceRecordIds.map((id) => state.data.sources.find((item) => item.sourceRecordId === id)).filter(Boolean);
  const source = sources[0];
  const evidence = state.data.evidence.find((item) => event.evidenceIds.includes(item.evidenceId));
  const watched = Boolean(watchByEvent(eventId));
  $("#drawerEyebrow").textContent = `${labels.channels[event.channel].name} · ${entity.canonicalName}`;
  $("#drawerTitle").textContent = event.title;
  const drawerWatch = $("#drawerWatch");
  drawerWatch.style.display = "grid";
  drawerWatch.dataset.currentEvent = eventId;
  drawerWatch.classList.toggle("saved", watched);
  drawerWatch.title = watched ? "取消跟踪" : "加入跟踪";
  drawerWatch.setAttribute("aria-label", watched ? "取消跟踪" : "加入跟踪");
  drawerWatch.innerHTML = icon(watched ? "bookmark-check" : "bookmark");
  $("#drawerBody").innerHTML = `<section class="detail-section"><div class="signal-meta">${badgeForStatus(event.eventStatus)}<span>${labels.business[event.business] || event.business}</span><span>${dateLabel(event.publishedAt)}发布</span><span>${dateLabel(event.discoveredAt)}发现</span></div><p class="detail-summary">${esc(event.summary)}</p></section>
    ${event.metrics?.length ? `<section class="detail-section"><h3>关键数字</h3><div class="detail-metrics">${event.metrics.map((item) => `<div class="detail-metric"><span>${esc(item.label)}</span><strong>${esc(item.value)}</strong></div>`).join("")}</div></section>` : ""}
    <section class="detail-section"><h3>业务判断</h3><div class="judgement"><strong>${esc(signal?.headline || "信息事件")}</strong><br>${esc(signal?.whyItMatters || "")}</div>${lead ? `<div class="next-action"><strong>下一步动作</strong><br>${esc(lead.nextAction)}${lead.dueAt ? `<br>复核时间：${dateLabel(lead.dueAt)}` : ""}</div>` : ""}</section>
    ${watchEditor(event)}
    <section class="detail-section"><h3>事件时间线</h3><div class="timeline">${event.timeline.map((item) => `<div class="timeline-item"><span>${esc(item.at)}</span><strong>${esc(item.label)}</strong></div>`).join("")}</div></section>
    <section class="detail-section"><h3>来源与证据 · ${sources.length}份</h3><div class="evidence-box"><p>${esc(evidence?.value || "证据字段待补充")}</p><div class="signal-meta"><span class="badge green">${esc(source?.sourceQuality || "unknown")}</span><span>${esc(source?.sourceName || "未知来源")}</span><span>${shortDateTime(source?.fetchedAt)}</span></div><div class="source-link-list">${sources.map((item, index) => `<a href="${esc(item.url)}" target="_blank" rel="noreferrer"><span>${String(index + 1).padStart(2, "0")}</span><strong>${esc(item.title)}</strong>${icon("external-link")}</a>`).join("")}</div></div></section>`;
  document.body.classList.add("drawer-open");
  $("#detailDrawer").setAttribute("aria-hidden", "false");
  refreshIcons();
}

function openEntity(entityId) {
  const entity = entityById(entityId);
  const events = state.data.events.filter((item) => item.primaryEntityId === entityId).sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt));
  $("#drawerEyebrow").textContent = `${entity.entityType} · ${entity.region}`;
  $("#drawerTitle").textContent = entity.canonicalName;
  $("#drawerWatch").style.display = "none";
  $("#drawerBody").innerHTML = `<section class="detail-section"><div class="signal-meta">${entity.universeTier ? `<span class="badge blue">${entity.universeTier}</span>` : ""}<span>${esc(entity.securityCode || entity.status)}</span><span>别名 ${entity.aliases.length}</span></div><p class="detail-summary">${esc(entity.aliases.join("、") || "无其他别名")}</p></section><section class="detail-section"><h3>年度事件时间线</h3><div class="timeline">${events.map((event) => `<div class="timeline-item" data-event-id="${event.eventId}"><span>${dateLabel(event.publishedAt)} · ${labels.channels[event.channel].name}</span><strong>${esc(event.title)}</strong></div>`).join("") || emptyState("暂无事件")}</div></section>`;
  document.body.classList.add("drawer-open");
  $("#detailDrawer").setAttribute("aria-hidden", "false");
  refreshIcons();
}

function closeDrawer() {
  document.body.classList.remove("drawer-open");
  $("#detailDrawer").setAttribute("aria-hidden", "true");
}

function setView(view) {
  state.view = view;
  $$(".view").forEach((item) => item.classList.toggle("active", item.dataset.viewPanel === view));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  document.body.classList.remove("sidebar-open");
  if (view === "listed") renderListed();
  if (view === "private") renderPrivate();
  if (view === "deals") renderDeals();
  if (view === "tender") renderTender();
  if (view === "watch") renderWatch();
  if (view === "signals") renderSignals();
  if (view === "leads") renderLeads();
  if (view === "annual") renderAnnual();
  if (view === "entities") renderEntities();
  if (view === "quality") renderQuality();
  refreshIcons();
  $("#mainContent").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setSlot(slot) {
  state.slot = slot;
  $$("[data-slot]").forEach((button) => button.classList.toggle("active", button.dataset.slot === slot));
  updateRunContext();
  renderDashboard();
  if (state.view !== "dashboard") setView(state.view);
  refreshIcons();
}

function updateRunContext() {
  const snapshot = currentSnapshot();
  const latestDate = state.listedWorkspace?.deepRead?.latestReportDate || state.privateFund?.asOf?.slice(0, 10) || snapshot.date;
  $("#reportDateLabel").textContent = `${dateLabel(latestDate)} · 最新`;
  $("#dataCutoff").textContent = latestDate;
  $("#navSignalCount").textContent = `${snapshot.activeSignalIds.length}条`;
  $("#navListedCount").textContent = `${state.listedUniverse?.counts.total ?? state.data.listedDaily.universeCount}家`;
  $("#navPrivateCount").textContent = `${state.privateFund?.summary.observationManagerCount ?? state.privateFund?.summary.managerCount ?? 0}家`;
  $("#navDealsCount").textContent = `${state.maProjects?.projectCount ?? 0}项`;
  $("#navTenderCount").textContent = `${state.tenderRuntime?.summary.activeOpportunityCount ?? state.data.tenderMonitor.activeOpportunityEventIds.length}项`;
  updateWatchCount();
  $("#sourceHealthLabel").textContent = "公开信息整理";
}

function exportAnnualCsv() {
  const header = ["日期", "主体", "事件", "频道", "业务", "状态", "关键数字", "截止", "质量"];
  const lines = getAnnualEvents().map((event) => [event.publishedAt.slice(0, 10), entityById(event.primaryEntityId).canonicalName, event.title, labels.channels[event.channel].name, labels.business[event.business] || event.business, labels.status[event.eventStatus] || event.eventStatus, event.metrics?.[0]?.value || "", event.deadlineAt?.slice(0, 10) || "", event.qualityStatus]);
  const csv = [header, ...lines].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `陕西资本市场-${state.annualFilters.channel}-2026.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(`已导出 ${lines.length} 条当前筛选结果`);
}

let toastTimer;
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function bindGlobalEvents() {
  document.addEventListener("click", (event) => {
    const removeTarget = event.target.closest("[data-watch-remove]");
    if (removeTarget) { event.stopPropagation(); removeWatch(removeTarget.dataset.watchRemove); renderDashboard(); if (state.view === "watch") renderWatch(); if (state.view === "listed") renderListed(); closeDrawer(); refreshIcons(); return; }
    const saveTarget = event.target.closest("[data-watch-save]");
    if (saveTarget) { event.stopPropagation(); saveWatchEditor(saveTarget.dataset.watchSave); return; }
    const addTarget = event.target.closest("[data-watch-add]");
    if (addTarget) { event.stopPropagation(); createWatch(addTarget.dataset.watchAdd); renderDashboard(); if (state.view === "listed") renderListed(); openEvent(addTarget.dataset.watchAdd); refreshIcons(); return; }
    const watchTarget = event.target.closest("[data-watch-event]");
    if (watchTarget) { event.stopPropagation(); toggleWatch(watchTarget.dataset.watchEvent); return; }
    const listedTab = event.target.closest("[data-listed-tab]");
    if (listedTab) { state.listedTab = listedTab.dataset.listedTab; renderListed(); refreshIcons(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const listedDeepRead = event.target.closest("[data-listed-deep-read]");
    if (listedDeepRead) { openListedDeepRead(listedDeepRead.dataset.listedDeepRead); return; }
    const listedWorkspaceStatus = event.target.closest("[data-listed-workspace-status]");
    if (listedWorkspaceStatus) { state.listedWorkspaceStatus = listedWorkspaceStatus.dataset.listedWorkspaceStatus; state.listedWorkspaceLimit = 60; renderListed(); refreshIcons(); return; }
    if (event.target.closest("[data-listed-load-more]")) { state.listedWorkspaceLimit += 60; renderListed(); refreshIcons(); return; }
    const financialMode = event.target.closest("[data-financial-mode]");
    if (financialMode) { state.listedFinancialMode = financialMode.dataset.financialMode; renderListed(); refreshIcons(); return; }
    const compareEntity = event.target.closest("[data-compare-entity]");
    if (compareEntity) {
      const entityId = compareEntity.dataset.compareEntity;
      state.listedCompareIds = state.listedCompareIds.includes(entityId) ? state.listedCompareIds.filter((id) => id !== entityId) : [...state.listedCompareIds, entityId];
      renderListed(); refreshIcons(); return;
    }
    const listedCompany = event.target.closest("[data-listed-company]");
    if (listedCompany) { state.listedCompanyId = listedCompany.dataset.listedCompany; renderListed(); refreshIcons(); return; }
    const tenderTab = event.target.closest("[data-tender-tab]");
    if (tenderTab) { state.tenderTab = tenderTab.dataset.tenderTab; renderTender(); refreshIcons(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const privateTab = event.target.closest("[data-private-tab]");
    if (privateTab) { state.privateTab = privateTab.dataset.privateTab; renderPrivate(); refreshIcons(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const privateQuarter = event.target.closest("[data-private-quarter]");
    if (privateQuarter) {
      const quarter = privateQuarter.dataset.privateQuarter;
      if (state.privateOpenQuarters.has(quarter)) state.privateOpenQuarters.delete(quarter);
      else state.privateOpenQuarters.add(quarter);
      renderPrivate(); refreshIcons(); return;
    }
    const privateManager = event.target.closest("[data-private-manager]");
    if (privateManager) { openPrivateManager(privateManager.dataset.privateManager); return; }
    const dealsTab = event.target.closest("[data-deals-tab]");
    if (dealsTab) { state.dealsTab = dealsTab.dataset.dealsTab; renderDeals(); refreshIcons(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const maProject = event.target.closest("[data-ma-project]");
    if (maProject) { openMaProject(maProject.dataset.maProject); return; }
    const preIpoEnterprise = event.target.closest("[data-preipo-enterprise]");
    if (preIpoEnterprise) { openPreIpo(preIpoEnterprise.dataset.preipoEnterprise); return; }
    const entityTab = event.target.closest("[data-entity-tab]");
    if (entityTab) { state.entityTab = entityTab.dataset.entityTab; renderEntities(); refreshIcons(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const eventTarget = event.target.closest("[data-event-id]");
    if (eventTarget) { openEvent(eventTarget.dataset.eventId); return; }
    const entityTarget = event.target.closest("[data-entity-id]");
    if (entityTarget) { openEntity(entityTarget.dataset.entityId); return; }
    const channelTarget = event.target.closest("[data-channel-jump]");
    if (channelTarget) { state.signalFilters.channel = channelTarget.dataset.channelJump; setView("signals"); return; }
    const viewTarget = event.target.closest("[data-view]");
    if (viewTarget) setView(viewTarget.dataset.view);
  });
  $$("[data-slot]").forEach((button) => button.addEventListener("click", () => setSlot(button.dataset.slot)));
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawerWatch").addEventListener("click", () => {
    const eventId = $("#drawerWatch").dataset.currentEvent;
    if (!eventId) return;
    toggleWatch(eventId);
    openEvent(eventId);
  });
  $("#drawerScrim").addEventListener("click", closeDrawer);
  $("#mobileMenu").addEventListener("click", () => document.body.classList.add("sidebar-open"));
  $("#sidebarScrim").addEventListener("click", () => document.body.classList.remove("sidebar-open"));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeDrawer(); document.body.classList.remove("sidebar-open"); } });
}

async function init() {
  try {
    const [response, tenderResponse, runtimeResponse, privateResponse, maResponse, preIpoResponse, relationshipsResponse, annualResponse, taxonomyResponse, universeResponse, eventStoreResponse, backfillResponse, listedWorkspaceResponse, privateWorkspaceResponse] = await Promise.all([fetch(DATA_URL, { cache: "no-store" }), fetch(TENDER_SOURCES_URL, { cache: "no-store" }), fetch(TENDER_RUNTIME_URL, { cache: "no-store" }), fetch(PRIVATE_FUND_URL, { cache: "no-store" }), fetch(MA_PROJECTS_URL, { cache: "no-store" }), fetch(PRE_IPO_URL, { cache: "no-store" }), fetch(RELATIONSHIPS_URL, { cache: "no-store" }), fetch(ANNUAL_INTELLIGENCE_URL, { cache: "no-store" }), fetch(LISTED_TAXONOMY_URL, { cache: "no-store" }), fetch(LISTED_UNIVERSE_URL, { cache: "no-store" }), fetch(EVENT_STORE_SUMMARY_URL, { cache: "no-store" }), fetch(BACKFILL_COVERAGE_URL, { cache: "no-store" }), fetch(LISTED_WORKSPACE_URL, { cache: "no-store" }), fetch(PRIVATE_FUND_WORKSPACE_URL, { cache: "no-store" })]);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    state.tenderRegistry = tenderResponse.ok ? await tenderResponse.json() : null;
    state.tenderRuntime = runtimeResponse.ok ? await runtimeResponse.json() : null;
    state.privateFund = privateResponse.ok ? await privateResponse.json() : null;
    state.maProjects = maResponse.ok ? await maResponse.json() : null;
    state.preIpo = preIpoResponse.ok ? await preIpoResponse.json() : null;
    state.relationships = relationshipsResponse.ok ? await relationshipsResponse.json() : null;
    state.annualIntelligence = annualResponse.ok ? await annualResponse.json() : null;
    state.listedTaxonomy = taxonomyResponse.ok ? await taxonomyResponse.json() : null;
    state.listedUniverse = universeResponse.ok ? await universeResponse.json() : null;
    state.eventStore = eventStoreResponse.ok ? await eventStoreResponse.json() : null;
    state.backfillCoverage = backfillResponse.ok ? await backfillResponse.json() : null;
    state.listedWorkspace = listedWorkspaceResponse.ok ? await listedWorkspaceResponse.json() : null;
    state.privateWorkspace = privateWorkspaceResponse.ok ? await privateWorkspaceResponse.json() : null;
    loadWatchItems();
    bindGlobalEvents();
    updateRunContext();
    renderDashboard();
    refreshIcons();
  } catch (error) {
    $("#view-dashboard").innerHTML = `<div class="audit-note">${icon("circle-alert")}<div><strong>数据加载失败</strong><br>${esc(error.message)}。请稍后重试。</div></div>`;
    refreshIcons();
  }
}

init();
