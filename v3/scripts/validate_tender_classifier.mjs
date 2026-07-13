import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { classifyTender } from "./classify_tender.mjs";
import { inferStage } from "./tender_stage.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(fs.readFileSync(path.join(here, "../data/sample/tender-classifier-fixtures.json"), "utf8"));
const stageFixtures = JSON.parse(fs.readFileSync(path.join(here, "../data/sample/tender-stage-fixtures.json"), "utf8"));
const errors = [];

for (const fixture of fixtures) {
  const result = classifyTender(fixture.record, new Date(fixture.now));
  if (result.classification !== fixture.expected) errors.push(`${fixture.fixtureId}: expected ${fixture.expected}, got ${result.classification}`);
  if (result.classification === "active_opportunity" && result.alertStatus !== "immediate") errors.push(`${fixture.fixtureId}: active opportunity must alert immediately`);
  if (result.classification === "history" && result.alertStatus !== "miss_review") errors.push(`${fixture.fixtureId}: late discovery must enter miss review`);
}

for (const fixture of stageFixtures) {
  const result = inferStage(fixture.record);
  if (result !== fixture.expected) errors.push(`${fixture.fixtureId}: expected stage ${fixture.expected}, got ${result}`);
}

if (errors.length) {
  console.error(`Tender classifier validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}

console.log(`Tender classifier validation passed: ${fixtures.length} deadline fixtures and ${stageFixtures.length} stage fixtures.`);
