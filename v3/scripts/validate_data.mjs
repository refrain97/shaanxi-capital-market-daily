import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { taxonomyTag } from "./listed_business_taxonomy.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const file = process.argv[2] || path.join(here, "../data/sample/dashboard-2026-07-10.json");
const data = JSON.parse(fs.readFileSync(file, "utf8"));
const tenderRegistry = JSON.parse(fs.readFileSync(path.join(here, "../config/tender-sources.json"), "utf8"));
const listedUniverse = JSON.parse(fs.readFileSync(path.join(here, "../data/listed/universe.json"), "utf8"));
const errors = [];

const requiredArrays = ["providers", "entities", "sources", "evidence", "events", "signals", "leads", "watchItems", "financialReports", "snapshots"];
for (const key of requiredArrays) {
  if (!Array.isArray(data[key])) errors.push(`SCHEMA: ${key} must be an array`);
}

const unique = (items, key, rule) => {
  const seen = new Set();
  for (const item of items || []) {
    if (!item[key]) errors.push(`${rule}: missing ${key}`);
    else if (seen.has(item[key])) errors.push(`${rule}: duplicate ${key} ${item[key]}`);
    seen.add(item[key]);
  }
  return seen;
};

const entityIds = unique(data.entities, "entityId", "ENT-003");
const sourceIds = unique(data.sources, "sourceRecordId", "SRC-001");
const evidenceIds = unique(data.evidence, "evidenceId", "SRC-003");
const eventIds = unique(data.events, "eventId", "DEDUP-001");
unique(data.events, "eventKey", "DEDUP-001");
const signalIds = unique(data.signals, "signalId", "DEDUP-002");
unique(data.leads, "leadId", "ACT-004");
unique(data.watchItems, "watchId", "WATCH-001");
const financialReportIds = unique(data.financialReports, "financialReportId", "FIN-001");
unique(data.snapshots, "snapshotId", "TIME-005");

const validChannels = new Set(["listed", "private_fund", "equity_financing", "ma", "tender", "soe"]);
for (const event of data.events || []) {
  if (!entityIds.has(event.primaryEntityId)) errors.push(`ENT-001: ${event.eventId} unknown entity`);
  if (!validChannels.has(event.channel)) errors.push(`SCHEMA: ${event.eventId} invalid channel`);
  if (!(event.sourceRecordIds || []).length) errors.push(`SRC-001: ${event.eventId} has no source`);
  for (const id of event.sourceRecordIds || []) if (!sourceIds.has(id)) errors.push(`SRC-001: ${event.eventId} unknown source ${id}`);
  for (const id of event.evidenceIds || []) if (!evidenceIds.has(id)) errors.push(`SRC-003: ${event.eventId} unknown evidence ${id}`);
  if (event.eventStatus === "action_window" && !event.deadlineAt) errors.push(`ACT-002: ${event.eventId} missing deadline`);
  if (event.channel === "tender" && event.eventStatus === "action_window" && new Date(event.deadlineAt) <= new Date(data.meta.generatedAt)) errors.push(`TIME-003: ${event.eventId} tender is expired`);
}

const signalsByEvent = new Map();
for (const signal of data.signals || []) {
  if (!eventIds.has(signal.eventId)) errors.push(`DEDUP-002: ${signal.signalId} unknown event`);
  if (signalsByEvent.has(signal.eventId)) errors.push(`DEDUP-002: multiple signals for ${signal.eventId}`);
  signalsByEvent.set(signal.eventId, signal.signalId);
  if (signal.actionable) {
    const lead = (data.leads || []).find((item) => item.signalId === signal.signalId);
    if (!lead) errors.push(`ACT-004: actionable ${signal.signalId} has no lead`);
  }
}

for (const lead of data.leads || []) {
  if (!signalIds.has(lead.signalId)) errors.push(`ACT-004: ${lead.leadId} unknown signal`);
  if (!entityIds.has(lead.targetEntityId)) errors.push(`ACT-004: ${lead.leadId} unknown target`);
  if (!lead.rationale || !lead.nextAction) errors.push(`ACT-004: ${lead.leadId} incomplete action`);
}

const activeWatchStatuses = new Set(["saved", "to_review", "following", "waiting"]);
const validWatchStatuses = new Set([...activeWatchStatuses, "resolved", "closed"]);
const watchedEventIds = new Set();
for (const watch of data.watchItems || []) {
  const event = (data.events || []).find((item) => item.eventId === watch.eventId);
  if (!event) errors.push(`WATCH-002: ${watch.watchId} unknown event ${watch.eventId}`);
  if (!entityIds.has(watch.entityId)) errors.push(`WATCH-003: ${watch.watchId} unknown entity ${watch.entityId}`);
  if (event && event.primaryEntityId !== watch.entityId) errors.push(`WATCH-003: ${watch.watchId} entity does not match event`);
  if (watchedEventIds.has(watch.eventId)) errors.push(`WATCH-001: duplicate watch event ${watch.eventId}`);
  watchedEventIds.add(watch.eventId);
  if (!validWatchStatuses.has(watch.watchStatus)) errors.push(`WATCH-004: ${watch.watchId} invalid status`);
  if (activeWatchStatuses.has(watch.watchStatus) && !Number.isFinite(Date.parse(watch.nextReviewAt))) errors.push(`WATCH-005: ${watch.watchId} active watch missing or invalid nextReviewAt`);
  if (!Array.isArray(watch.stateHistory) || !watch.stateHistory.length) errors.push(`WATCH-006: ${watch.watchId} missing state history`);
  else if (watch.stateHistory.at(-1).status !== watch.watchStatus) errors.push(`WATCH-006: ${watch.watchId} latest state does not match status`);
  const createdAt = Date.parse(watch.createdAt);
  const updatedAt = Date.parse(watch.updatedAt);
  if (!Number.isFinite(createdAt) || !Number.isFinite(updatedAt) || updatedAt < createdAt) errors.push(`WATCH-007: ${watch.watchId} invalid update chronology`);
}

for (const entity of data.entities || []) {
  if (entity.universeTier === "L3" && ["比亚迪", "海格通信"].includes(entity.canonicalName)) errors.push(`LST-008: excluded L3 entity ${entity.canonicalName}`);
}

if (!data.listedDaily || !Array.isArray(data.listedDaily.items)) {
  errors.push("LST-010: listedDaily and items are required");
} else {
  const dailyItemIds = unique(data.listedDaily.items, "dailyItemId", "LST-010");
  if (data.listedDaily.universeCount !== listedUniverse.counts.total) errors.push("LST-010: complete listed universe count mismatch");
  if (data.listedDaily.retrievedUniverseCount !== listedUniverse.retrievalCoverage.cninfoCompanyCount) errors.push("LST-010: retrieved universe count mismatch");
  if (Object.entries(listedUniverse.counts).filter(([key]) => key !== "total").some(([key, value]) => data.listedDaily.universeTierCounts?.[key] !== value)) errors.push("LST-010: universe tier counts mismatch");
  const dailyEventIds = new Set();
  const dailySourceIds = [];
  const dailyEntityIds = new Set();
  for (const item of data.listedDaily.items) {
    const event = (data.events || []).find((candidate) => candidate.eventId === item.eventId);
    if (!event || event.channel !== "listed") errors.push(`LST-010: ${item.dailyItemId} must reference a listed event`);
    if (event && event.primaryEntityId !== item.entityId) errors.push(`LST-010: ${item.dailyItemId} entity mismatch`);
    if (dailyEventIds.has(item.eventId)) errors.push(`LST-011: duplicate daily event ${item.eventId}`);
    dailyEventIds.add(item.eventId);
    dailyEntityIds.add(item.entityId);
    if (!item.effective || !item.inclusionReason) errors.push(`LST-012: ${item.dailyItemId} missing effective inclusion reason`);
    const businessTag = taxonomyTag(item.rmCategory, item.rmSubcategory);
    if (!businessTag) errors.push(`LST-013: ${item.dailyItemId} unknown RM category/subcategory`);
    if (businessTag && item.businessPriority !== businessTag.businessPriority) errors.push(`LST-013: ${item.dailyItemId} business priority mismatch`);
    if (businessTag && JSON.stringify(item.targetObjects) !== JSON.stringify(businessTag.targetObjects)) errors.push(`LST-013: ${item.dailyItemId} target objects mismatch`);
    for (const id of item.sourceRecordIds || []) {
      dailySourceIds.push(id);
      if (!sourceIds.has(id)) errors.push(`LST-010: ${item.dailyItemId} unknown source ${id}`);
      if (event && !event.sourceRecordIds.includes(id)) errors.push(`LST-011: ${item.dailyItemId} source not attached to event ${id}`);
    }
  }
  if (dailyItemIds.size !== data.listedDaily.effectiveEventCount) errors.push("LST-010: effective event count does not reconcile");
  if (dailySourceIds.length !== data.listedDaily.announcementCount) errors.push("LST-010: announcement count does not reconcile");
  if (new Set(dailySourceIds).size !== dailySourceIds.length) errors.push("LST-011: one disclosure appears in multiple daily items");
  if (dailyEntityIds.size !== data.listedDaily.coveredCompanyCount) errors.push("LST-010: covered company count does not reconcile");
}

for (const report of data.financialReports || []) {
  const event = (data.events || []).find((item) => item.eventId === report.eventId);
  if (!event || event.channel !== "listed") errors.push(`FIN-002: ${report.financialReportId} must reference a listed event`);
  if (!entityIds.has(report.entityId) || (event && event.primaryEntityId !== report.entityId)) errors.push(`FIN-002: ${report.financialReportId} entity mismatch`);
  for (const id of report.sourceRecordIds || []) if (!sourceIds.has(id)) errors.push(`FIN-003: ${report.financialReportId} unknown source ${id}`);
  if (report.netProfitLower !== null && report.netProfitUpper !== null && report.netProfitLower > report.netProfitUpper) errors.push(`FIN-004: ${report.financialReportId} invalid net profit range`);
  if (report.adjustedNetProfitLower !== null && report.adjustedNetProfitUpper !== null && report.adjustedNetProfitLower > report.adjustedNetProfitUpper) errors.push(`FIN-004: ${report.financialReportId} invalid adjusted profit range`);
  if (!report.currency || !report.period || !report.disclosureType) errors.push(`FIN-005: ${report.financialReportId} incomplete reporting basis`);
}

if (!data.tenderMonitor) {
  errors.push("TEN-010: tenderMonitor is required");
} else {
  const monitor = data.tenderMonitor;
  if (monitor.scanIntervalMinutes < 30 || monitor.scanIntervalMinutes > 60) errors.push("TEN-010: scan interval must be 30 to 60 minutes");
  if (monitor.scanIntervalMinutes !== tenderRegistry.scanIntervalMinutes) errors.push("TEN-010: monitor and source registry intervals differ");
  if (monitor.schedulerEnabled !== tenderRegistry.schedulerEnabled) errors.push("TEN-010: monitor and source registry scheduler status differ");
  const activeIds = new Set(monitor.activeOpportunityEventIds || []);
  for (const id of activeIds) {
    const event = (data.events || []).find((item) => item.eventId === id);
    if (!event || event.channel !== "tender" || event.eventStatus !== "action_window") errors.push(`TEN-011: active opportunity ${id} is not an actionable tender event`);
    if (!event?.deadlineAt || new Date(event.deadlineAt) <= new Date(monitor.asOf)) errors.push(`TEN-011: active opportunity ${id} has no valid future deadline`);
  }
  unique(monitor.projects, "tenderProjectId", "TEN-012");
  for (const project of monitor.projects || []) {
    const event = (data.events || []).find((item) => item.eventId === project.eventId);
    if (!event || event.channel !== "tender") errors.push(`TEN-012: ${project.tenderProjectId} missing tender event`);
    if (event && event.primaryEntityId !== project.procurementEntityId) errors.push(`TEN-012: ${project.tenderProjectId} entity mismatch`);
    if (["candidate", "award", "contract", "completed"].includes(project.firstDiscoveryStage) && project.alertStatus === "immediate") errors.push(`TEN-013: ${project.tenderProjectId} result stage cannot alert as opportunity`);
    if (project.remainingHoursAtDiscovery <= 0 && project.alertStatus === "immediate") errors.push(`TEN-013: ${project.tenderProjectId} expired at discovery`);
    if (project.missReview && project.alertStatus !== "miss_review") errors.push(`TEN-014: ${project.tenderProjectId} miss review status mismatch`);
  }
  unique(monitor.findings, "findingId", "TEN-015");
  for (const finding of monitor.findings || []) {
    if (["candidate", "award", "contract", "completed"].includes(finding.stage) && finding.classification === "active_opportunity") errors.push(`TEN-015: ${finding.findingId} result finding entered opportunity area`);
    if (finding.sourceQuality === "discovery_only" && finding.classification === "active_opportunity") errors.push(`TEN-016: ${finding.findingId} search summary entered opportunity area`);
    if (finding.eligibilityStatus === "excluded" && finding.alertStatus !== "none") errors.push(`TEN-017: ${finding.findingId} excluded item generated alert`);
  }
  unique(monitor.scanRuns, "tenderScanRunId", "TEN-018");
}

const tenderSourceIds = unique(tenderRegistry.sources, "sourceId", "TEN-019");
if (tenderSourceIds.size < 3) errors.push("TEN-019: official tender source registry is too narrow");
for (const source of tenderRegistry.sources || []) {
  if (!source.url.startsWith("https://")) errors.push(`TEN-019: ${source.sourceId} must use HTTPS`);
  if (source.scanIntervalMinutes < 30 || source.scanIntervalMinutes > 60) errors.push(`TEN-019: ${source.sourceId} invalid interval`);
}

for (const snapshot of data.snapshots || []) {
  for (const id of [...snapshot.newEventIds, ...snapshot.updatedEventIds]) if (!eventIds.has(id)) errors.push(`TIME-005: ${snapshot.snapshotId} unknown event ${id}`);
  for (const id of snapshot.activeSignalIds) if (!signalIds.has(id)) errors.push(`DEDUP-002: ${snapshot.snapshotId} unknown signal ${id}`);
}

const providerIds = new Set(data.providers.map((item) => item.providerId));
for (const expected of ["wind_codex", "ifind_codex"]) if (!providerIds.has(expected)) errors.push(`PROV-001: missing ${expected} probe`);

if (errors.length) {
  console.error(`V3 data validation failed (${errors.length})`);
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`V3 data validation passed: ${data.events.length} events, ${data.signals.length} signals, ${data.leads.length} leads, ${data.watchItems.length} watch items, ${data.listedDaily.items.length} listed daily items, ${financialReportIds.size} financial records, ${data.tenderMonitor.activeOpportunityEventIds.length} active tender opportunities, ${data.snapshots.length} snapshots.`);
