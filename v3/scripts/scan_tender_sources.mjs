import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { classifyTender } from "./classify_tender.mjs";
import { validateTenderRuntime } from "./tender_runtime_validation.mjs";
import { inferStage } from "./tender_stage.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const registryPath = path.join(root, "config/tender-sources.json");
const runtimeRoot = path.join(root, "data/tender");
const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
const now = new Date();
const shanghaiParts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
}).formatToParts(now).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
const shanghaiDay = `${shanghaiParts.year}-${shanghaiParts.month}-${shanghaiParts.day}`;
const runId = `tender-live-${shanghaiDay}T${shanghaiParts.hour}-${shanghaiParts.minute}-${shanghaiParts.second}`;
const writeEnabled = !process.argv.includes("--dry-run");

const serviceKeywords = [...new Set([
  ...registry.keywordGroups.services,
  "债券承销", "公司债", "企业债", "中期票据", "资产证券化", "ABS", "REITs"
])];
const securitiesFit = /(主承销|联席主承销|债券承销|承销团|受托管理人|财务顾问|融资顾问|投资顾问|资产证券化|\bABS\b|\bREITs\b|上市辅导)/i;

const stripHtml = (value = "") => value
  .replace(/<[^>]*>/g, "")
  .replace(/&nbsp;|&#160;/g, " ")
  .replace(/&ldquo;|&rdquo;/g, '"')
  .replace(/&mdash;/g, "-")
  .replace(/&[a-z]+;/gi, " ")
  .replace(/\s+/g, " ")
  .trim();

const hash = (value) => crypto.createHash("sha256").update(value).digest("hex");

function projectFingerprint(title) {
  const normalized = stripHtml(title)
    .replace(/^[【\[][^】\]]+[】\]]/g, "")
    .replace(/陕铁集团/g, "陕西省铁路集团有限公司")
    .replace(/国企采购采购公告|交易公告|公开招标公告|竞争性磋商公告|招标公告|采购公告|中标候选人公示|中标结果公告|中标结果公示|中标公告|中标公示|成交结果公告|成交公示|变更公告|更正公告|终止公告|废标公告/g, "")
    .replace(/二次|重新招标|[\[\]【】（）()\-—_·，。、“”'"\s]/g, "")
    .toLowerCase();
  return hash(normalized).slice(0, 24);
}

function parseDateTime(text, labels) {
  const labelPattern = labels.join("|");
  const patterns = [
    new RegExp(`(?:${labelPattern})[^0-9]{0,24}(20\\d{2})\\s*[年\\-/\.]\\s*(\\d{1,2})\\s*[月\\-/\.]\\s*(\\d{1,2})\\s*日?[^0-9]{0,8}(\\d{1,2})\\s*(?::|时)\\s*(\\d{1,2})?`, "i"),
    new RegExp(`(?:${labelPattern})[^0-9]{0,24}(20\\d{2})\\s*[年\\-/\.]\\s*(\\d{1,2})\\s*[月\\-/\.]\\s*(\\d{1,2})\\s*日?`, "i")
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) continue;
    const [, year, month, day, hour = "23", minute = "59"] = match;
    return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}T${hour.padStart(2, "0")}:${minute.padStart(2, "0")}:00+08:00`;
  }
  return null;
}

function parsePurchaser(text) {
  const match = text.match(/(?:招标人|采购人|项目业主)[（(]?[^）)]*[）)]?为[：:]?\s*([^，。；;]{2,80})/);
  return match ? match[1].replace(/建设资金.*$/, "").trim() : "待回源提取";
}

function normalizeRecord(source, record) {
  const title = stripHtml(record.title);
  const content = stripHtml(record.content);
  const stage = inferStage(record);
  const deadlineAt = parseDateTime(content, ["投标文件递交截止时间", "投标截止时间", "响应文件提交截止时间", "递交截止时间", "报名截止时间"]);
  const openingAt = parseDateTime(content, ["开标时间", "开启时间"]);
  const publishedAt = record.webdate ? `${record.webdate.replace(" ", "T")}+08:00` : null;
  const sourceUrl = new URL(record.linkurl, source.url).href;
  const normalized = {
    recordId: `${source.sourceId}:${record.infoid || hash(sourceUrl).slice(0, 20)}`,
    sourceId: source.sourceId,
    sourceQuality: source.authority,
    sourceUrl,
    title,
    purchaser: parsePurchaser(content),
    stage,
    eligibilityStatus: securitiesFit.test(`${title} ${content}`) ? "eligible" : "excluded",
    publishedAt,
    discoveredAt: now.toISOString(),
    deadlineAt,
    openingAt,
    category: record.categoryname || "",
    region: record.zhuanzai || record.diqu || "陕西",
    contentExcerpt: content.slice(0, 1800)
  };
  const classification = classifyTender(normalized, now);
  return {
    ...normalized,
    projectFingerprint: projectFingerprint(title),
    ...classification,
    contentHash: hash(JSON.stringify({ title, content, stage, deadlineAt, openingAt }))
  };
}

function decodeHtml(value = "") {
  return value.replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
}

function parseCebRows(source, html, stage, keyword) {
  const records = [];
  for (const row of html.match(/<tr>[\s\S]*?<\/tr>/g) || []) {
    const detail = row.match(/urlOpen\('([^']+)'\)[\s\S]*?title="([^"]+)"/);
    if (!detail) continue;
    const [, uuid, rawTitle] = detail;
    const title = stripHtml(decodeHtml(rawTitle));
    const area = row.match(/<span\s+title\s*=\s*"([^"]+)"[\s\S]*?【/)?.[1]?.trim() || "";
    if (area && !/陕西/.test(area) && !/陕西/.test(title)) continue;
    const publishedRaw = row.match(/<td[^>]*name="imgShow"[^>]*id="([^"]+)"/)?.[1] || row.match(/\b20\d{2}-\d{2}-\d{2}\b/)?.[0];
    const openingRaw = row.match(/<td[^>]*name="openTime"[^>]*id="([^"]+)"/)?.[1] || null;
    const publishedAt = publishedRaw ? `${publishedRaw.includes(" ") ? publishedRaw.replace(" ", "T") : `${publishedRaw}T00:00:00`}+08:00` : null;
    const deadlineAt = openingRaw ? `${openingRaw.replace(" ", "T")}+08:00` : null;
    const titleStage = inferStage({ title, categoryname: "" });
    const effectiveStage = ["terminated", "candidate", "award"].includes(titleStage) ? titleStage : stage;
    const record = {
      recordId: `${source.sourceId}:${uuid}`,
      sourceId: source.sourceId,
      sourceQuality: source.authority,
      sourceUrl: `https://ctbpsp.com/#/bulletinDetail?uuid=${uuid}&inpvalue=&dataSource=0&tenderAgency=`,
      title,
      purchaser: /陕西金资/.test(title) ? "陕西金融资产管理股份有限公司" : "待回源提取",
      stage: effectiveStage,
      eligibilityStatus: securitiesFit.test(title) ? "eligible" : "excluded",
      publishedAt,
      discoveredAt: now.toISOString(),
      deadlineAt,
      openingAt: deadlineAt,
      category: `中国招标投标公共服务平台 · ${keyword}`,
      region: area || "陕西",
      contentExcerpt: title,
      projectFingerprint: projectFingerprint(title),
      contentHash: hash(JSON.stringify({ uuid, title, stage: effectiveStage, publishedAt, deadlineAt }))
    };
    records.push({ ...record, ...classifyTender(record, now) });
  }
  return records;
}

async function scanCebSource(source) {
  const stageEndpoints = { announcement: "bulletin", change: "change", candidate: "candidate", award: "result" };
  const records = new Map();
  const queries = [];
  for (const [stage, endpoint] of Object.entries(stageEndpoints)) {
    for (const keyword of serviceKeywords) {
      const query = new URL(`${source.searchEndpoint}/${endpoint}.html`);
      query.searchParams.set("searchDate", shanghaiDay);
      query.searchParams.set("dates", "30");
      query.searchParams.set("categoryId", stage === "announcement" ? "88" : stage === "change" ? "89" : stage === "candidate" ? "91" : "90");
      query.searchParams.set("industryName", "");
      query.searchParams.set("area", "");
      query.searchParams.set("status", "");
      query.searchParams.set("publishMedia", "");
      query.searchParams.set("sourceInfo", "");
      query.searchParams.set("showStatus", "");
      query.searchParams.set("word", keyword);
      const startedAt = Date.now();
      const response = await fetchWithTimeout(query);
      const html = await response.text();
      const parsed = parseCebRows(source, html, stage, keyword);
      parsed.forEach((record) => records.set(record.recordId, record));
      queries.push({ keyword, stage, httpStatus: response.status, recordCount: parsed.length, elapsedMs: Date.now() - startedAt });
    }
  }
  return { status: "PASS", queries, records: [...records.values()] };
}

function fullTextPayload(keyword, pageSize = 20) {
  return {
    esdsid: "1", token: "", pn: 0, rn: pageSize, sdt: "", edt: "", wd: keyword,
    inc_wd: "", exc_wd: "", fields: "title", cnum: "001", sort: '{"webdate":"0"}',
    ssort: "title", cl: 5000, cutIngore: "title;linkurl", terminal: "", condition: [],
    time: [], highlights: "title", statistics: null, unionCondition: null, accuracy: "",
    noParticiple: "1", searchRange: [], isBusiness: "1"
  };
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal, redirect: "follow", headers: { "User-Agent": "Shaanxi-Capital-Market-V3/0.4", ...(options.headers || {}) } });
  } finally {
    clearTimeout(timer);
  }
}

async function scanFullTextSource(source) {
  const records = new Map();
  const queries = [];
  for (const keyword of serviceKeywords) {
    const startedAt = new Date();
    const response = await fetchWithTimeout(source.searchEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fullTextPayload(keyword))
    });
    const outer = await response.json();
    const result = JSON.parse(outer.content).result;
    queries.push({ keyword, httpStatus: response.status, totalCount: Number(result.totalcount || 0), elapsedMs: Date.now() - startedAt.getTime() });
    for (const record of result.records || []) {
      const normalized = normalizeRecord(source, record);
      records.set(normalized.recordId, normalized);
    }
  }
  return { status: "PASS", queries, records: [...records.values()] };
}

async function probeSource(source) {
  const startedAt = new Date();
  try {
    const response = await fetchWithTimeout(source.url);
    const body = await response.text();
    return {
      sourceId: source.sourceId,
      status: response.ok ? "PASS" : "FAIL_HTTP",
      httpStatus: response.status,
      finalUrl: response.url,
      contentType: response.headers.get("content-type"),
      contentBytes: Buffer.byteLength(body),
      contentHash: hash(body),
      elapsedMs: Date.now() - startedAt.getTime()
    };
  } catch (error) {
    return { sourceId: source.sourceId, status: "FAIL_NETWORK", error: error.message, elapsedMs: Date.now() - startedAt.getTime() };
  }
}

const sourceRuns = [];
const allRecords = new Map();
for (const source of registry.sources) {
  if (source.adapter === "sxggzy_fulltext_v1") {
    try {
      const result = await scanFullTextSource(source);
      result.records.forEach((record) => allRecords.set(record.recordId, record));
      sourceRuns.push({ sourceId: source.sourceId, adapter: source.adapter, status: result.status, queries: result.queries, recordCount: result.records.length });
    } catch (error) {
      sourceRuns.push({ sourceId: source.sourceId, adapter: source.adapter, status: "FAIL_ADAPTER", error: error.message, recordCount: 0 });
    }
  } else if (source.adapter === "ceb_html_search_v1") {
    try {
      const result = await scanCebSource(source);
      result.records.forEach((record) => allRecords.set(record.recordId, record));
      sourceRuns.push({ sourceId: source.sourceId, adapter: source.adapter, status: result.status, queries: result.queries, recordCount: result.records.length });
    } catch (error) {
      sourceRuns.push({ sourceId: source.sourceId, adapter: source.adapter, status: "FAIL_ADAPTER", error: error.message, recordCount: 0 });
    }
  } else {
    sourceRuns.push({ ...(await probeSource(source)), adapter: source.adapter });
  }
}

const records = [...allRecords.values()].sort((a, b) => new Date(b.publishedAt || 0) - new Date(a.publishedAt || 0));
const previousPath = path.join(runtimeRoot, "scans/latest.json");
const previous = fs.existsSync(previousPath) ? JSON.parse(fs.readFileSync(previousPath, "utf8")) : { records: [] };
const previousById = new Map(previous.records.map((record) => [record.recordId, record]));
const newRecordIds = records.filter((record) => !previousById.has(record.recordId)).map((record) => record.recordId);
const changedRecordIds = records.filter((record) => previousById.has(record.recordId) && previousById.get(record.recordId).contentHash !== record.contentHash).map((record) => record.recordId);
const activeOpportunities = [...new Map(records.filter((record) => record.classification === "active_opportunity").map((record) => [record.projectFingerprint, record])).values()];
const pending = records.filter((record) => record.classification === "pending" && record.eligibilityStatus !== "excluded");
const history = records.filter((record) => record.classification === "history");

const runtime = {
  schemaVersion: "0.1",
  runId,
  generatedAt: now.toISOString(),
  scanIntervalMinutes: registry.scanIntervalMinutes,
  sourceRuns,
  summary: {
    sourcePass: sourceRuns.filter((run) => run.status === "PASS").length,
    sourceFail: sourceRuns.filter((run) => run.status !== "PASS").length,
    recordCount: records.length,
    newCount: newRecordIds.length,
    changedCount: changedRecordIds.length,
    activeOpportunityCount: activeOpportunities.length,
    pendingCount: pending.length,
    historyCount: history.length,
    excludedCount: records.filter((record) => record.classification === "excluded").length
  },
  newRecordIds,
  changedRecordIds,
  activeOpportunities,
  pending,
  history,
  records
};

const runtimeErrors = validateTenderRuntime(runtime, registry);
if (runtimeErrors.length) throw new Error(`Tender runtime validation failed: ${runtimeErrors.join(" | ")}`);
runtime.validation = { status: "PASS", ruleCount: 7 };

if (writeEnabled) {
  const day = shanghaiDay;
  const runDir = path.join(runtimeRoot, "runs", day);
  const scanDir = path.join(runtimeRoot, "scans");
  const alertDir = path.join(runtimeRoot, "alerts", day);
  fs.mkdirSync(runDir, { recursive: true });
  fs.mkdirSync(scanDir, { recursive: true });
  fs.mkdirSync(alertDir, { recursive: true });
  fs.writeFileSync(path.join(runDir, `${runId}.json`), `${JSON.stringify(runtime, null, 2)}\n`);
  fs.writeFileSync(previousPath, `${JSON.stringify(runtime, null, 2)}\n`);
  const alert = { runId, generatedAt: runtime.generatedAt, items: activeOpportunities };
  fs.writeFileSync(path.join(alertDir, `${runId}.json`), `${JSON.stringify(alert, null, 2)}\n`);
  fs.mkdirSync(path.join(runtimeRoot, "alerts"), { recursive: true });
  fs.writeFileSync(path.join(runtimeRoot, "alerts/latest.json"), `${JSON.stringify(alert, null, 2)}\n`);
}

console.log(JSON.stringify({ runId, writeEnabled, ...runtime.summary }, null, 2));
