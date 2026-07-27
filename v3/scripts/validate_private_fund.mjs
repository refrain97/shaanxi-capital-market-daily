import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const snapshotPath = path.join(here, "../data/private-fund/snapshots/latest.json");
const data = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
const errors = [];
const unique = (values) => new Set(values).size === values.length;

if (data.summary.managerCount !== data.managerUniverse.length || data.summary.observationManagerCount !== data.managerUniverse.length) errors.push("managerCount must reconcile to managerUniverse");
if (data.summary.territorialManagerCount !== data.managerUniverse.filter((item) => item.universeTier === "PF1").length) errors.push("territorialManagerCount must reconcile to PF1");
if (data.summary.relatedManagerCount !== data.managerUniverse.filter((item) => item.universeTier === "PF2").length) errors.push("relatedManagerCount must reconcile to PF2");
if (data.summary.territorialManagerCount !== 82 || data.summary.relatedManagerCount !== 1 || data.summary.managerCount !== 83) errors.push("approved private-fund baseline must be PF1 82 + PF2 1 = 83");
if (!unique(data.managerUniverse.map((item) => item.registerNo))) errors.push("manager universe registerNo must be unique");
if (!data.managerUniverse.some((item) => item.registerNo === "P1020607" && item.universeTier === "PF2" && item.monitoringPriority === "important")) errors.push("Baopu Rongyi must remain an important PF2 target");
if (data.managerUniverse.some((item) => !["PF1", "PF2"].includes(item.universeTier) || item.monitoringPriority !== "important")) errors.push("every approved manager must have a valid tier and important priority");
if (data.summary.ytdProductCount !== data.custodianSummary.reduce((sum, item) => sum + item.productCount, 0)) errors.push("ytdProductCount must reconcile to custodian product counts");
if (data.newProducts.length !== data.summary.newProductCount) errors.push("newProductCount does not match newProducts length");
if (data.topManagers.length !== data.summary.topManagerCount) errors.push("topManagerCount does not match topManagers length");
if (!unique(data.topManagers.map((item) => item.registerNo))) errors.push("top manager registerNo must be unique");
if (!unique(data.topManagers.map((item) => item.rank))) errors.push("top manager rank must be unique");
if (data.topManagers.some((item, index) => item.rank !== index + 1)) errors.push("top manager ranks must be contiguous and ordered");
if (data.topManagers.some((item) => !Number.isInteger(item.activityScore) || item.activityScore < 0)) errors.push("activityScore must be a non-negative integer");
if (data.topManagers.some((item) => item.activityScore !== Object.values(item.scoreEvidence.components).reduce((sum, value) => sum + value, 0))) errors.push("activityScore must equal its disclosed components");
if (data.topManagers.some((item) => !item.detailUrl?.startsWith("https://gs.amac.org.cn/") || !item.executives.length)) errors.push("every covered top manager needs AMAC detail URL and executives");
if (data.summary.personnelCoveredCount !== data.topManagers.filter((item) => item.executives.length).length) errors.push("personnelCoveredCount mismatch");
if (data.summary.personnelComparisonStatus === "baseline_created" && data.personnelChanges.length) errors.push("baseline snapshot must not claim personnel changes");
if (data.newProducts.some((item) => !item.fundNo || !item.sourceUrl?.startsWith("https://gs.amac.org.cn/") || !item.filingDate)) errors.push("new products require fundNo, filing date and AMAC source");
if (data.newProducts.some((item) => item.reactivationCandidate && !/候选/.test(item.reactivationReason || ""))) errors.push("reactivation candidate must carry an explicit candidate caveat");
if (data.locationObservations.some((item) => item.classification !== "location_observation" || !/不得直接表述/.test(item.note))) errors.push("cross-province addresses must remain observations, not migration claims");
if (!unique(data.businessTaxonomy.map((item) => item.code)) || data.businessTaxonomy.length !== 6) errors.push("RM private PB taxonomy must contain six unique types");
if (!data.universeRules.automaticExclusions.some((item) => item.includes("学习或任职"))) errors.push("weak personnel-only links must remain automatically excluded");

if (errors.length) {
  console.error(`Private fund validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}

console.log(`Private fund validation passed: ${data.topManagers.length} ranked managers, ${data.summary.personnelCoveredCount} personnel profiles, ${data.newProducts.length} new product, ${data.locationObservations.length} location observations.`);
