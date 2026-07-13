import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { inferStage } from "./tender_stage.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const registry = JSON.parse(fs.readFileSync(path.join(root, "config/tender-sources.json"), "utf8"));
const backfillConfig = JSON.parse(fs.readFileSync(path.join(root, "config/backfill-2026.json"), "utf8"));
const source = registry.sources.find((item) => item.adapter === "ceb_html_search_v1");
const outputRoot = path.join(root, "data/backfill/tender");
const runAt = new Date();
const todayInShanghai = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit"
}).format(runAt);
const startDate = process.env.V3_BACKFILL_START || backfillConfig.startDate;
const endDate = process.env.V3_BACKFILL_END || backfillConfig.endDate || todayInShanghai;
const searchDays = Math.ceil((new Date(`${endDate}T00:00:00Z`) - new Date(`${startDate}T00:00:00Z`)) / 86400000) + 1;
const maxPages = Number(process.env.CEB_MAX_PAGES || 200);
const concurrency = Number(process.env.CEB_CONCURRENCY || 5);
const areaCode = "610000";
const keywords = ["主承销商", "债券承销", "财务顾问", "资产证券化", "上市辅导"];
const stageEndpoints = { announcement: "bulletin", change: "change", candidate: "candidate", award: "result" };

if (!source) throw new Error("Missing ceb_html_search_v1 source adapter");

const stripHtml = (value = "") => value
  .replace(/<[^>]*>/g, "")
  .replace(/&nbsp;|&#160;/g, " ")
  .replace(/&ldquo;|&rdquo;/g, '"')
  .replace(/&mdash;/g, "-")
  .replace(/&[a-z]+;/gi, " ")
  .replace(/\s+/g, " ")
  .trim();
const decodeHtml = (value = "") => value
  .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
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

function buildUrl(endpoint, keyword, page) {
  const url = new URL(`${source.searchEndpoint}/${endpoint}.html`);
  for (const [name, value] of Object.entries({
    searchDate: endDate,
    dates: String(Math.min(searchDays, 365)),
    categoryId: endpoint === "bulletin" ? "88" : endpoint === "change" ? "89" : endpoint === "candidate" ? "91" : "90",
    industryName: "",
    area: areaCode,
    status: "",
    publishMedia: "",
    sourceInfo: "",
    showStatus: "",
    word: keyword,
    page: String(page)
  })) url.searchParams.set(name, value);
  return url;
}

function parseRows(html, requestedStage, keyword) {
  const records = [];
  for (const row of html.match(/<tr>[\s\S]*?<\/tr>/g) || []) {
    const detail = row.match(/urlOpen\('([^']+)'\)[\s\S]*?title="([^"]+)"/);
    if (!detail) continue;
    const [, uuid, rawTitle] = detail;
    const title = stripHtml(decodeHtml(rawTitle));
    if (!title.includes(keyword)) continue;
    const publishedRaw = row.match(/<td[^>]*name="imgShow"[^>]*id="([^"]+)"/)?.[1] || row.match(/\b20\d{2}-\d{2}-\d{2}\b/)?.[0];
    if (!publishedRaw) continue;
    const publishedDay = publishedRaw.slice(0, 10);
    if (publishedDay < startDate || publishedDay > endDate) continue;
    const openingRaw = row.match(/<td[^>]*name="openTime"[^>]*id="([^"]+)"/)?.[1] || null;
    const publishedAt = `${publishedRaw.includes(" ") ? publishedRaw.replace(" ", "T") : `${publishedRaw}T00:00:00`}+08:00`;
    const deadlineAt = openingRaw ? `${openingRaw.replace(" ", "T")}+08:00` : null;
    const titleStage = inferStage({ title, categoryname: "" });
    const stage = ["terminated", "candidate", "award", "change"].includes(titleStage) ? titleStage : requestedStage;
    records.push({
      recordId: `${source.sourceId}:${uuid}`,
      sourceId: source.sourceId,
      sourceQuality: source.authority,
      sourceUrl: `https://ctbpsp.com/#/bulletinDetail?uuid=${uuid}&inpvalue=&dataSource=0&tenderAgency=`,
      title,
      purchaser: /陕西金资/.test(title) ? "陕西金融资产管理股份有限公司" : "待回源提取",
      stage,
      eligibilityStatus: "eligible",
      publishedAt,
      discoveredAt: runAt.toISOString(),
      discoveryMode: "backfill",
      deadlineAt,
      openingAt: deadlineAt,
      category: `中国招标投标公共服务平台 · ${keyword}`,
      region: "陕西",
      matchedKeywords: [keyword],
      contentExcerpt: title,
      projectFingerprint: projectFingerprint(title),
      contentHash: hash(JSON.stringify({ uuid, title, stage, publishedAt, deadlineAt }))
    });
  }
  return records;
}

function lastPage(html) {
  return Number(html.match(/turnPage\((\d+)\);">末页/)?.[1] || 1);
}

async function fetchText(url, attempt = 1) {
  try {
    const response = await fetch(url, { headers: { "User-Agent": "Shaanxi-Capital-Market-V3/0.5" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.text();
  } catch (error) {
    if (attempt >= 3) throw error;
    await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
    return fetchText(url, attempt + 1);
  }
}

async function runPool(tasks) {
  const results = [];
  let cursor = 0;
  async function worker() {
    while (cursor < tasks.length) {
      const index = cursor++;
      results[index] = await tasks[index]();
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, tasks.length) }, worker));
  return results;
}

fs.mkdirSync(path.join(outputRoot, "raw"), { recursive: true });
const records = new Map();
const queries = [];

for (const [requestedStage, endpoint] of Object.entries(stageEndpoints)) {
  for (const keyword of keywords) {
    const firstHtml = await fetchText(buildUrl(endpoint, keyword, 1));
    const availablePages = lastPage(firstHtml);
    const pageLimit = Math.min(availablePages, maxPages);
    const pages = [firstHtml, ...(await runPool(Array.from({ length: Math.max(0, pageLimit - 1) }, (_, index) => async () => (
      fetchText(buildUrl(endpoint, keyword, index + 2))
    ))))];
    let matchedCount = 0;
    for (const html of pages) {
      const parsed = parseRows(html, requestedStage, keyword);
      matchedCount += parsed.length;
      for (const record of parsed) {
        const previous = records.get(record.recordId);
        if (previous) {
          record.matchedKeywords = [...new Set([...previous.matchedKeywords, ...record.matchedKeywords])];
        }
        records.set(record.recordId, record);
      }
    }
    queries.push({ requestedStage, keyword, availablePages, fetchedPages: pageLimit, resultCapHit: availablePages > maxPages, matchedCount });
    console.log(`${requestedStage} / ${keyword}: ${matchedCount} matches from ${pageLimit}/${availablePages} pages`);
  }
}

const normalized = [...records.values()].sort((a, b) => new Date(a.publishedAt) - new Date(b.publishedAt));
const output = {
  schemaVersion: "0.1",
  channel: "tender",
  novelty: "backfill",
  period: { startDate, endDate },
  generatedAt: runAt.toISOString(),
  source: { sourceId: source.sourceId, name: source.name, url: source.url, authority: source.authority },
  status: queries.some((query) => query.resultCapHit) ? "NORMALIZED_WITH_SEARCH_RESULT_CAP" : "NORMALIZED",
  limits: queries.some((query) => query.resultCapHit) ? ["平台单次检索页数超过本次安全抓取上限，结果不是全量声明"] : [],
  summary: {
    queryCount: queries.length,
    fetchedPageCount: queries.reduce((sum, query) => sum + query.fetchedPages, 0),
    resultCapQueryCount: queries.filter((query) => query.resultCapHit).length,
    recordCount: normalized.length,
    projectCount: new Set(normalized.map((record) => record.projectFingerprint)).size
  },
  queries,
  records: normalized
};

fs.writeFileSync(path.join(outputRoot, "raw", "ceb-query-ledger-2026.json"), `${JSON.stringify({ generatedAt: runAt.toISOString(), queries }, null, 2)}\n`);
fs.writeFileSync(path.join(outputRoot, "normalized-ceb-2026.json"), `${JSON.stringify(output, null, 2)}\n`);
console.log(JSON.stringify(output.summary, null, 2));
