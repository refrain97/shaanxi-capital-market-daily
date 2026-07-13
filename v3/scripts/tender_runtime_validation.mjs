export function validateTenderRuntime(runtime, registry) {
  const errors = [];
  const sourceIds = new Set(registry.sources.map((item) => item.sourceId));
  const runSourceIds = new Set();
  for (const run of runtime.sourceRuns || []) {
    if (!sourceIds.has(run.sourceId)) errors.push(`TEN-RUN-001: unknown source ${run.sourceId}`);
    if (runSourceIds.has(run.sourceId)) errors.push(`TEN-RUN-001: duplicate source run ${run.sourceId}`);
    runSourceIds.add(run.sourceId);
  }
  for (const sourceId of sourceIds) if (!runSourceIds.has(sourceId)) errors.push(`TEN-RUN-001: missing source run ${sourceId}`);

  const recordIds = new Set();
  for (const record of runtime.records || []) {
    if (!record.recordId || recordIds.has(record.recordId)) errors.push(`TEN-RUN-002: duplicate or missing record ${record.recordId}`);
    recordIds.add(record.recordId);
    if (!record.contentHash || !record.sourceUrl?.startsWith("https://")) errors.push(`TEN-RUN-003: ${record.recordId} missing hash or HTTPS source`);
    if (record.classification === "active_opportunity") {
      if (!["announcement", "change", "registration", "bidding"].includes(record.stage)) errors.push(`TEN-RUN-004: ${record.recordId} invalid opportunity stage`);
      if (record.eligibilityStatus !== "eligible" || record.sourceQuality === "discovery_only") errors.push(`TEN-RUN-004: ${record.recordId} invalid opportunity qualification`);
      if (!record.deadlineAt || record.remainingHours <= 0) errors.push(`TEN-RUN-004: ${record.recordId} expired opportunity`);
    }
    if (["candidate", "award", "contract", "completed", "terminated"].includes(record.stage) && record.classification === "active_opportunity") errors.push(`TEN-RUN-005: ${record.recordId} result stage entered opportunities`);
  }

  const summaryChecks = {
    recordCount: runtime.records.length,
    sourcePass: runtime.sourceRuns.filter((item) => item.status === "PASS").length,
    sourceFail: runtime.sourceRuns.filter((item) => item.status !== "PASS").length,
    activeOpportunityCount: runtime.activeOpportunities.length,
    pendingCount: runtime.records.filter((item) => item.classification === "pending" && item.eligibilityStatus !== "excluded").length,
    historyCount: runtime.records.filter((item) => item.classification === "history").length,
    excludedCount: runtime.records.filter((item) => item.classification === "excluded").length
  };
  for (const [key, expected] of Object.entries(summaryChecks)) if (runtime.summary[key] !== expected) errors.push(`TEN-RUN-006: ${key} expected ${expected}, got ${runtime.summary[key]}`);
  for (const id of [...runtime.newRecordIds, ...runtime.changedRecordIds]) if (!recordIds.has(id)) errors.push(`TEN-RUN-007: diff references unknown record ${id}`);
  if (new Set(runtime.newRecordIds).size !== runtime.newRecordIds.length || new Set(runtime.changedRecordIds).size !== runtime.changedRecordIds.length) errors.push("TEN-RUN-007: duplicate diff ids");
  return errors;
}
