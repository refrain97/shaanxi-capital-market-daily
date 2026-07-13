import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { classifyTender } from "./classify_tender.mjs";
import { inferStage } from "./tender_stage.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const registry = JSON.parse(fs.readFileSync(path.join(root, "config/tender-sources.json"), "utf8"));
const backfillConfig = JSON.parse(fs.readFileSync(path.join(root, "config/backfill-2026.json"), "utf8"));
const outputRoot = path.join(root, "data/backfill/tender");
const source = registry.sources.find((item) => item.adapter === "sxggzy_fulltext_v1");

if (!source) throw new Error("Missing sxggzy_fulltext_v1 source adapter");

const runAt = new Date();
const todayInShanghai = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit"
}).format(runAt);
const startDate = process.env.V3_BACKFILL_START || backfillConfig.startDate;
const endDate = process.env.V3_BACKFILL_END || backfillConfig.endDate || todayInShanghai;
const pageSize = 100;
const keywords = [...new Set([
  ...registry.keywordGroups.products,
  ...registry.keywordGroups.services,
  "债券承销",
  "公司债",
  "企业债",
  "中期票据",
  "资产证券化",
  "ABS",
  "REITs"
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
    new RegExp(`(?:${labelPattern})[^0-9]{0,24}(20\\d{2})\\s*[年\\-/\\.]\\s*(\\d{1,2})\\s*[月\\-/\\.]\\s*(\\d{1,2})\\s*日?[^0-9]{0,8}(\\d{1,2})\\s*(?::|时)\\s*(\\d{1,2})?`, "i"),
    new RegExp(`(?:${labelPattern})[^0-9]{0,24}(20\\d{2})\\s*[年\\-/\\.]\\s*(\\d{1,2})\\s*[月\\-/\\.]\\s*(\\d{1,2})\\s*日?`, "i")
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

function normalizeRecord(record, matchedKeywords) {
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
    discoveredAt: runAt.toISOString(),
    discoveryMode: "backfill",
    deadlineAt,
    openingAt,
    category: record.categoryname || "",
    region: record.zhuanzai || record.diqu || "陕西",
    matchedKeywords,
    contentExcerpt: content.slice(0, 1800),
    projectFingerprint: projectFingerprint(title),
    contentHash: hash(JSON.stringify({ title, content, stage, deadlineAt, openingAt }))
  };
  return { ...normalized, ...classifyTender(normalized, runAt) };
}

function monthRanges(start, end) {
  const ranges = [];
  let cursor = new Date(`${start}T00:00:00Z`);
  const limit = new Date(`${end}T00:00:00Z`);
  while (cursor <= limit) {
    const monthStart = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth(), 1));
    const monthEnd = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 0));
    const from = monthStart < new Date(`${start}T00:00:00Z`) ? new Date(`${start}T00:00:00Z`) : monthStart;
    const to = monthEnd > limit ? limit : monthEnd;
    ranges.push([from.toISOString().slice(0, 10), to.toISOString().slice(0, 10)]);
    cursor = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1));
  }
  return ranges;
}

function payload(keyword, from, to, offset) {
  return {
    esdsid: "1", token: "", pn: offset, rn: pageSize, sdt: from, edt: to, wd: keyword,
    inc_wd: "", exc_wd: "", fields: "title", cnum: "001", sort: '{"webdate":"0"}',
    ssort: "title", cl: 5000, cutIngore: "title;linkurl", terminal: "", condition: [],
    time: [], highlights: "title", statistics: null, unionCondition: null, accuracy: "",
    noParticiple: "1", searchRange: [], isBusiness: "1"
  };
}

async function fetchPage(keyword, from, to, offset) {
  const response = await fetch(source.searchEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "User-Agent": "Shaanxi-Capital-Market-V3/0.5" },
    body: JSON.stringify(payload(keyword, from, to, offset))
  });
  if (!response.ok) throw new Error(`${keyword} ${from}-${to} offset ${offset}: HTTP ${response.status}`);
  const outer = await response.json();
  return JSON.parse(outer.content).result;
}

fs.mkdirSync(path.join(outputRoot, "raw"), { recursive: true });
const rawRecords = new Map();
const queryRuns = [];

for (const [from, to] of monthRanges(startDate, endDate)) {
  const monthRecords = new Map();
  const monthQueries = [];
  for (const keyword of keywords) {
    let offset = 0;
    let totalCount = 0;
    let fetchedCount = 0;
    do {
      const result = await fetchPage(keyword, from, to, offset);
      totalCount = Number(result.totalcount || 0);
      const records = result.records || [];
      for (const record of records) {
        const recordId = record.infoid || hash(`${record.linkurl}|${record.title}`);
        const existing = monthRecords.get(recordId) || rawRecords.get(recordId);
        const keywordSet = new Set(existing?.matchedKeywords || []);
        keywordSet.add(keyword);
        const item = { ...record, matchedKeywords: [...keywordSet] };
        monthRecords.set(recordId, item);
        rawRecords.set(recordId, item);
      }
      fetchedCount += records.length;
      offset += pageSize;
      if (!records.length) break;
    } while (offset < totalCount);
    const metadata = { keyword, from, to, totalCount, fetchedCount };
    monthQueries.push(metadata);
    queryRuns.push(metadata);
  }
  fs.writeFileSync(
    path.join(outputRoot, "raw", `sxggzy-${from}_${to}.json`),
    `${JSON.stringify({ schemaVersion: "0.1", source, from, to, retrievedAt: runAt.toISOString(), queries: monthQueries, records: [...monthRecords.values()] }, null, 2)}\n`
  );
  console.log(`${from}..${to}: ${monthRecords.size} unique raw records`);
}

const normalized = [...rawRecords.values()]
  .map((record) => normalizeRecord(record, record.matchedKeywords || []))
  .sort((a, b) => new Date(a.publishedAt || 0) - new Date(b.publishedAt || 0));
if (!queryRuns.length) throw new Error(`No tender queries generated for ${startDate}..${endDate}`);
const eligible = normalized.filter((record) => record.eligibilityStatus === "eligible");
const byProject = new Map();
for (const record of eligible) {
  if (!byProject.has(record.projectFingerprint)) byProject.set(record.projectFingerprint, []);
  byProject.get(record.projectFingerprint).push(record);
}

const projects = [...byProject.entries()].map(([projectFingerprint, records]) => {
  records.sort((a, b) => new Date(a.publishedAt || 0) - new Date(b.publishedAt || 0));
  const announcement = records.find((record) => record.stage === "announcement");
  const deadlineAt = announcement?.deadlineAt || records.find((record) => record.deadlineAt)?.deadlineAt || null;
  const publicationWindowConfirmed = Boolean(announcement?.publishedAt && deadlineAt && new Date(deadlineAt) > new Date(announcement.publishedAt));
  return {
    projectFingerprint,
    title: announcement?.title || records[0].title,
    purchaser: records.find((record) => record.purchaser !== "待回源提取")?.purchaser || "待回源提取",
    firstPublishedAt: records[0].publishedAt,
    firstAnnouncementAt: announcement?.publishedAt || null,
    deadlineAt,
    latestStage: records.at(-1).stage,
    timelineCount: records.length,
    recordIds: records.map((record) => record.recordId),
    historicalStatus: announcement ? (publicationWindowConfirmed ? "PUBLICATION_WINDOW_CONFIRMED" : "ANNOUNCEMENT_NEEDS_DEADLINE_REVIEW") : "ANNOUNCEMENT_NOT_FOUND",
    backfillOnly: true
  };
}).sort((a, b) => new Date(a.firstPublishedAt || 0) - new Date(b.firstPublishedAt || 0));

const normalizedOutput = {
  schemaVersion: "0.1",
  channel: "tender",
  novelty: "backfill",
  period: { startDate, endDate },
  generatedAt: runAt.toISOString(),
  source: { sourceId: source.sourceId, name: source.name, url: source.url, authority: source.authority },
  status: "PRIMARY_SOURCE_NORMALIZED_SECONDARY_SOURCE_PENDING",
  limits: ["中国招标投标公共服务平台的年度分页复核尚未完成", "正文时间提取失败的项目仍需人工复核"],
  summary: {
    keywordCount: keywords.length,
    queryCount: queryRuns.length,
    rawRecordCount: normalized.length,
    eligibleRecordCount: eligible.length,
    projectCount: projects.length,
    announcementFoundCount: projects.filter((project) => project.firstAnnouncementAt).length,
    publicationWindowConfirmedCount: projects.filter((project) => project.historicalStatus === "PUBLICATION_WINDOW_CONFIRMED").length,
    deadlineReviewCount: projects.filter((project) => project.historicalStatus === "ANNOUNCEMENT_NEEDS_DEADLINE_REVIEW").length,
    announcementMissingCount: projects.filter((project) => project.historicalStatus === "ANNOUNCEMENT_NOT_FOUND").length
  },
  records: eligible,
  projects
};

fs.writeFileSync(path.join(outputRoot, "normalized-2026.json"), `${JSON.stringify(normalizedOutput, null, 2)}\n`);
console.log(JSON.stringify(normalizedOutput.summary, null, 2));
