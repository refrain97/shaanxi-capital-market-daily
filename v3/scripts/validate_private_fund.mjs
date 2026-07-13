import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const snapshotPath = path.join(here, "../data/private-fund/snapshots/latest.json");
const data = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
const errors = [];
const unique = (values) => new Set(values).size === values.length;

if (data.summary.managerCount !== 82) errors.push(`managerCount expected 82, got ${data.summary.managerCount}`);
if (data.summary.ytdProductCount !== 27) errors.push(`ytdProductCount expected 27, got ${data.summary.ytdProductCount}`);
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

if (errors.length) {
  console.error(`Private fund validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}

console.log(`Private fund validation passed: ${data.topManagers.length} ranked managers, ${data.summary.personnelCoveredCount} personnel profiles, ${data.newProducts.length} new product, ${data.locationObservations.length} location observations.`);
