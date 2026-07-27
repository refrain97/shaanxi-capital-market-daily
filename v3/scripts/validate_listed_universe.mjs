import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const universe = JSON.parse(fs.readFileSync(path.join(root, "data/listed/universe.json"), "utf8"));
const errors = [];
const codes = universe.entities.map((item) => item.securityCode);
const tierCount = (tier) => universe.entities.filter((item) => item.universeTier === tier).length;
if (universe.counts.total !== universe.entities.length || universe.counts.total !== 110) errors.push("LST-UNI-001: complete universe must reconcile to 110");
if (universe.counts.L1 !== 85 || tierCount("L1") !== 85) errors.push("LST-UNI-002: L1 must contain 85 Shaanxi A-share companies");
if (universe.counts.L2 !== 14 || tierCount("L2") !== 14) errors.push("LST-UNI-003: L2 must contain 14 verified HK-listed companies");
if (universe.counts.L3 !== 11 || tierCount("L3") !== 11) errors.push("LST-UNI-004: L3 must contain 11 manually verified related listed companies");
if (new Set(codes).size !== codes.length) errors.push("LST-UNI-005: security codes must be unique across tiers");
const excludedNames = new Set(universe.excluded.map((item) => item.canonicalName));
if (universe.entities.some((item) => excludedNames.has(item.canonicalName))) errors.push("LST-UNI-006: excluded companies entered universe");
const allowedRelations = new Set(["operating_base", "headquarters_office", "strategic_shareholding", "controlling_shareholding", "control_rights", "group_industry_affiliation"]);
if (universe.entities.filter((item) => item.universeTier === "L3").some((item) => !allowedRelations.has(item.relationType) || item.relationStrength !== "material" || item.monitoringPriority !== "important")) errors.push("LST-UNI-007: every L3 target requires a material reviewed relation and important monitoring priority");
if (universe.retrievalCoverage.resolvedSubjectCount !== 110 || universe.entities.some((item) => !item.cninfoOrgId || !item.cninfoQueryCode)) errors.push("LST-UNI-008: all 110 subjects require resolved announcement identifiers");
if (!universe.retrievalCoverage.note.includes("HKEX")) errors.push("LST-UNI-009: HKEX completeness review boundary must remain visible");
if (!["彤程新材", "北方铜业", "广誉远", "佳力奇", "金天钛业", "明阳电路", "菲林格尔"].every((name) => excludedNames.has(name))) errors.push("LST-UNI-010: weak-relation exclusions are incomplete");

if (errors.length) {
  console.error(`Listed universe validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}
console.log(`Listed universe validation passed: ${universe.counts.total} total, L1 ${universe.counts.L1}, L2 ${universe.counts.L2}, L3 ${universe.counts.L3}.`);
