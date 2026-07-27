import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const inputPaths = [
  path.join(root, "data/backfill/tender/normalized-2026.json"),
  path.join(root, "data/backfill/tender/normalized-ceb-2026.json")
];
const outputPath = path.join(root, "data/backfill/tender/merged-2026.json");
const inputs = inputPaths.map((file) => JSON.parse(fs.readFileSync(file, "utf8")));

const stripHtml = (value = "") => value.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
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

const recordsById = new Map();
for (const input of inputs) {
  for (const record of input.records || []) {
    const fingerprint = projectFingerprint(record.title);
    recordsById.set(record.recordId, { ...record, projectFingerprint: fingerprint });
  }
}

const groups = new Map();
for (const record of recordsById.values()) {
  if (!groups.has(record.projectFingerprint)) groups.set(record.projectFingerprint, []);
  groups.get(record.projectFingerprint).push(record);
}

const stageOrder = { announcement: 1, change: 2, terminated: 3, candidate: 4, award: 5 };
const projects = [...groups.entries()].map(([projectFingerprint, records]) => {
  records.sort((a, b) => new Date(a.publishedAt || 0) - new Date(b.publishedAt || 0));
  const announcements = records.filter((record) => record.stage === "announcement");
  const firstAnnouncement = announcements[0];
  const deadlines = records.map((record) => record.deadlineAt).filter(Boolean).sort();
  const latest = [...records].sort((a, b) => {
    const dateDiff = new Date(b.publishedAt || 0) - new Date(a.publishedAt || 0);
    return dateDiff || (stageOrder[b.stage] || 0) - (stageOrder[a.stage] || 0);
  })[0];
  const sourceIds = [...new Set(records.map((record) => record.sourceId))];
  const publicationWindowConfirmed = Boolean(firstAnnouncement?.publishedAt && deadlines[0] && new Date(deadlines[0]) > new Date(firstAnnouncement.publishedAt));
  return {
    candidateId: `tender-backfill-${projectFingerprint}`,
    projectFingerprint,
    title: firstAnnouncement?.title || records[0].title,
    purchaser: records.find((record) => record.purchaser && record.purchaser !== "待回源提取")?.purchaser || "待回源提取",
    firstPublishedAt: records[0].publishedAt,
    firstAnnouncementAt: firstAnnouncement?.publishedAt || null,
    deadlineAt: deadlines.at(-1) || null,
    latestPublishedAt: latest.publishedAt,
    latestStage: latest.stage,
    sourceIds,
    sourceRecordIds: records.map((record) => record.recordId),
    timelineCount: records.length,
    historicalStatus: firstAnnouncement ? (publicationWindowConfirmed ? "PUBLICATION_WINDOW_CONFIRMED" : "ANNOUNCEMENT_NEEDS_DEADLINE_REVIEW") : "ANNOUNCEMENT_NOT_FOUND",
    noveltyStatus: "backfill",
    normalizationStatus: "timeline_grouped_source_review_pending",
    timeline: records.map((record) => ({
      at: record.publishedAt,
      stage: record.stage,
      title: record.title,
      recordId: record.recordId,
      sourceId: record.sourceId,
      sourceUrl: record.sourceUrl
    }))
  };
}).sort((a, b) => new Date(a.firstPublishedAt || 0) - new Date(b.firstPublishedAt || 0));

const output = {
  schemaVersion: "0.1",
  channel: "tender",
  novelty: "backfill",
  period: inputs[0].period,
  generatedAt: new Date().toISOString(),
  status: "DEDUPED_PROJECT_TIMELINES_REVIEW_PENDING",
  limits: [...new Set(inputs.flatMap((input) => input.limits || []))],
  sources: inputs.map((input) => input.source),
  summary: {
    sourceCount: inputs.length,
    recordCount: recordsById.size,
    projectCount: projects.length,
    announcementFoundCount: projects.filter((project) => project.firstAnnouncementAt).length,
    publicationWindowConfirmedCount: projects.filter((project) => project.historicalStatus === "PUBLICATION_WINDOW_CONFIRMED").length,
    deadlineReviewCount: projects.filter((project) => project.historicalStatus === "ANNOUNCEMENT_NEEDS_DEADLINE_REVIEW").length,
    announcementMissingCount: projects.filter((project) => project.historicalStatus === "ANNOUNCEMENT_NOT_FOUND").length
  },
  records: [...recordsById.values()].sort((a, b) => new Date(a.publishedAt || 0) - new Date(b.publishedAt || 0)),
  projects
};

fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`);
console.log(JSON.stringify(output.summary, null, 2));
