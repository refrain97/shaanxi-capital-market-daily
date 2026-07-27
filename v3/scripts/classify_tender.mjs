const opportunityStages = new Set(["announcement", "change", "registration", "bidding"]);
const resultStages = new Set(["candidate", "award", "contract", "completed", "terminated"]);

export function classifyTender(record, now = new Date()) {
  const discoveredAt = new Date(record.discoveredAt);
  const deadlineAt = record.deadlineAt ? new Date(record.deadlineAt) : null;
  const remainingHoursAtDiscovery = deadlineAt ? Math.floor((deadlineAt - discoveredAt) / 3600000) : null;
  const remainingHours = deadlineAt ? Math.floor((deadlineAt - now) / 3600000) : null;

  if (record.eligibilityStatus === "excluded") {
    return { classification: "excluded", alertStatus: "none", remainingHoursAtDiscovery, remainingHours };
  }
  if (resultStages.has(record.stage)) {
    return { classification: "history", alertStatus: "miss_review", remainingHoursAtDiscovery, remainingHours };
  }
  if (!opportunityStages.has(record.stage)) {
    return { classification: "pending", alertStatus: "review", remainingHoursAtDiscovery, remainingHours };
  }
  if (!deadlineAt || !Number.isFinite(deadlineAt.getTime())) {
    return { classification: "pending", alertStatus: "review", remainingHoursAtDiscovery: null, remainingHours: null };
  }
  if (remainingHoursAtDiscovery <= 0) {
    return { classification: "history", alertStatus: "miss_review", remainingHoursAtDiscovery, remainingHours };
  }
  if (record.eligibilityStatus !== "eligible" || record.sourceQuality === "discovery_only") {
    return { classification: "pending", alertStatus: "review", remainingHoursAtDiscovery, remainingHours };
  }
  return { classification: "active_opportunity", alertStatus: "immediate", remainingHoursAtDiscovery, remainingHours };
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  const input = JSON.parse(process.argv[2]);
  console.log(JSON.stringify(classifyTender(input), null, 2));
}
