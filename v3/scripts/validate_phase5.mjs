import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const ma = JSON.parse(fs.readFileSync(path.join(root, "data/ma-projects/latest.json"), "utf8"));
const preipo = JSON.parse(fs.readFileSync(path.join(root, "data/pre-ipo/latest.json"), "utf8"));
const dashboard = JSON.parse(fs.readFileSync(path.join(root, "data/sample/dashboard-2026-07-10.json"), "utf8"));
const errors = [];
const unique = (values) => new Set(values).size === values.length;

if (ma.projectCount !== ma.projects.length || ma.projectCount !== 25) errors.push("M&A project count must reconcile to 25");
if (!unique(ma.projects.map((item) => item.maProjectId))) errors.push("M&A project IDs must be unique");
if (Object.values(ma.stageCounts).reduce((sum, value) => sum + value, 0) !== ma.projectCount) errors.push("M&A stage counts must reconcile");
if (ma.officialSourceProjectCount + ma.sourceBackfillCount !== ma.projectCount) errors.push("M&A source status counts must reconcile");
if (ma.projects.some((item) => !item.milestones.length || !unique(item.milestones.map((node) => node.milestoneId)))) errors.push("every M&A project needs unique milestones");
if (ma.projects.filter((item) => item.sourceStatus === "official").some((item) => !item.sourceRecords.length || item.sourceRecords.some((source) => !source.url?.startsWith("https://")))) errors.push("official M&A projects require HTTPS source records");
if (ma.projects.filter((item) => item.sourceStatus !== "official").some((item) => item.sourceStatus !== "needs_source_backfill")) errors.push("legacy projects without sources must be visibly queued for backfill");

if (preipo.reserveTotalCount !== 530) errors.push("2026 reserve total must be 530");
if (preipo.tierCounts.A !== 80 || preipo.tierCounts.B !== 120 || preipo.tierCounts.C !== 330) errors.push("2026 reserve tier counts are incorrect");
const aTier = preipo.profiles.filter((item) => item.reserveTier === "A");
if (aTier.length !== 80 || preipo.aTierTranscribedCount !== 80) errors.push("A-tier priority pool must contain 80 profiles");
if (!unique(aTier.map((item) => item.name)) || !unique(aTier.map((item) => item.reserveRank))) errors.push("A-tier names and ranks must be unique");
if (aTier.some((item, index) => item.reserveRank !== index + 1)) errors.push("A-tier ranks must be contiguous");
if (preipo.profiles.some((item) => !item.milestones.length || !item.latestMilestoneAt)) errors.push("every pre-IPO profile needs a dated milestone");
if (preipo.profiles.some((item) => item.latestMilestoneAt !== item.milestones.map((node) => node.at).sort().at(-1))) errors.push("pre-IPO latest milestone must be the chronological maximum");
if (preipo.financingRecords.some((item) => !item.sourceUrl?.startsWith("https://") || item.verificationStatus !== "verified")) errors.push("confirmed financing records require verified HTTPS sources");

const maikeaote = dashboard.entities.find((item) => item.entityId === "ent-maikeaote");
const listingEvent = dashboard.events.find((item) => item.eventId === "evt-20260611-maikeaote-hearing");
const listingSignal = dashboard.signals.find((item) => item.signalId === "sig-maikeaote");
if (maikeaote?.securityCode !== "02335.HK" || maikeaote?.entityType !== "listed_company") errors.push("Micot entity must be promoted to HK listed company");
if (listingEvent?.eventStatus !== "completed" || listingEvent?.timeline.at(-1)?.at !== "2026-06-24") errors.push("Micot listing journey must update the existing event through listing date");
if (listingSignal?.actionable !== false || listingSignal?.signalStatus !== "completed") errors.push("completed Micot listing signal must not remain actionable");

if (errors.length) {
  console.error(`Phase 5 validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}

console.log(`Phase 5 validation passed: ${ma.projectCount} M&A projects, ${ma.officialSourceProjectCount} sourced, ${preipo.aTierTranscribedCount} A-tier enterprises, ${preipo.financingRecords.length} financing record.`);
