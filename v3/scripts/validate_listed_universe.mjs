import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const universe = JSON.parse(fs.readFileSync(path.join(root, "data/listed/universe.json"), "utf8"));
const errors = [];
const codes = universe.entities.map((item) => item.securityCode);
const tierCount = (tier) => universe.entities.filter((item) => item.universeTier === tier).length;
if (universe.counts.total !== universe.entities.length || universe.counts.total !== 117) errors.push("LST-UNI-001: complete universe must reconcile to 117");
if (universe.counts.L1 !== 85 || tierCount("L1") !== 85) errors.push("LST-UNI-002: L1 must contain 85 Shaanxi A-share companies");
if (universe.counts.L2 !== 14 || tierCount("L2") !== 14) errors.push("LST-UNI-003: L2 must contain 14 verified HK-listed companies");
if (universe.counts.L3 !== 18 || tierCount("L3") !== 18) errors.push("LST-UNI-004: L3 must contain 18 related listed companies");
if (new Set(codes).size !== codes.length) errors.push("LST-UNI-005: security codes must be unique across tiers");
if (universe.entities.some((item) => ["比亚迪", "海格通信"].includes(item.canonicalName))) errors.push("LST-UNI-006: excluded companies entered universe");
if (universe.entities.filter((item) => item.universeTier === "L3" && item.inclusionReason === "持股大于10%").some((item) => !(item.relatedHoldingPct > 10))) errors.push("LST-UNI-007: holding-only L3 inclusion must be strictly above 10%");
if (universe.retrievalCoverage.cninfoCompanyCount !== 85 || !universe.retrievalCoverage.note.includes("只覆盖L1")) errors.push("LST-UNI-008: retrieval coverage must remain distinct from complete universe");

if (errors.length) {
  console.error(`Listed universe validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}
console.log(`Listed universe validation passed: ${universe.counts.total} total, L1 ${universe.counts.L1}, L2 ${universe.counts.L2}, L3 ${universe.counts.L3}.`);
