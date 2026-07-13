import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const network = JSON.parse(fs.readFileSync(path.join(root, "data/relationships/latest.json"), "utf8"));
const annual = JSON.parse(fs.readFileSync(path.join(root, "data/annual/2026.json"), "utf8"));
const errors = [];
const unique = (items) => new Set(items).size === items.length;
const nodes = new Set(network.nodes.map((item) => item.nodeId));

if (network.summary.nodeCount !== network.nodes.length || !unique(network.nodes.map((item) => item.nodeId))) errors.push("relationship nodes must be unique and reconcile");
if (network.summary.edgeCount !== network.edges.length || !unique(network.edges.map((item) => item.edgeId))) errors.push("relationship edges must be unique and reconcile");
if (network.edges.some((edge) => !nodes.has(edge.sourceNodeId) || !nodes.has(edge.targetNodeId))) errors.push("every relationship edge must reference existing nodes");
if (network.edges.some((edge) => !edge.evidenceType || (edge.sourceUrl && !edge.sourceUrl.startsWith("https://")))) errors.push("relationship evidence must be typed and URLs must use HTTPS");
if (!network.edges.some((edge) => edge.relationType === "executive") || !network.edges.some((edge) => edge.relationType === "invested_in") || !network.edges.some((edge) => edge.relationType === "linked_ma_project")) errors.push("required cross-channel relationship types are missing");
if (annual.year !== 2026 || annual.metrics.reserveEnterprises !== 530 || annual.metrics.aTierProfiles !== 80) errors.push("annual reserve metrics are invalid");
if (annual.metrics.maProjects !== 25 || annual.metrics.privateManagers !== 82 || annual.metrics.privateYtdProducts !== 27) errors.push("annual channel metrics do not reconcile");
if (Object.values(annual.monthlySeries).some((series) => series.length !== 12 || series.some((item, index) => item.month !== `2026-${String(index + 1).padStart(2, "0")}`))) errors.push("every annual series must contain 12 ordered months");
if (!Array.isArray(annual.dataBoundaries) || annual.dataBoundaries.length < 4) errors.push("annual data boundaries must be visible");

if (errors.length) {
  console.error(`Phase 6 validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}
console.log(`Phase 6 validation passed: ${network.nodes.length} nodes, ${network.edges.length} evidence edges, ${Object.keys(annual.metrics).length} annual metrics.`);
