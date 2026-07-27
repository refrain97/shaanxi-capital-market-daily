import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateTenderRuntime } from "./tender_runtime_validation.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const runtimePath = process.argv[2] || path.join(here, "../data/tender/scans/latest.json");
const registryPath = path.join(here, "../config/tender-sources.json");
const runtime = JSON.parse(fs.readFileSync(runtimePath, "utf8"));
const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
const errors = validateTenderRuntime(runtime, registry);

if (errors.length) {
  console.error(`Tender runtime validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}

console.log(`Tender runtime validation passed: ${runtime.records.length} records, ${runtime.summary.activeOpportunityCount} active opportunities, ${runtime.sourceRuns.length} source runs.`);
