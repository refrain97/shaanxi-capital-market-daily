import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const samplePath = path.join(here, "../data/sample/dashboard-2026-07-10.json");
const registryPath = path.join(here, "../config/tender-sources.json");
const data = JSON.parse(fs.readFileSync(samplePath, "utf8"));
const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));

data.tenderMonitor = {
  asOf: "2026-07-10T17:30:00+08:00",
  mode: "prototype",
  scanIntervalMinutes: 60,
  schedulerEnabled: registry.schedulerEnabled,
  schedulerStatus: registry.schedulerEnabled ? "running" : "not_enabled",
  sourceRegistryFile: "config/tender-sources.json",
  activeOpportunityEventIds: [],
  projects: [
    {
      tenderProjectId: "tender-project-jinzi-tech-bond-2026",
      eventId: "evt-20260121-jinzi-tender",
      projectCode: "SX-STB-2026-002",
      procurementEntityId: "ent-shaanxi-jinzi",
      serviceType: "bond_underwriting",
      stage: "award",
      eligibilityStatus: "eligible",
      sourceQuality: "authoritative",
      fitRationale: "采购内容为科创债主承销商选聘，证券公司具备直接参与适配性。",
      qualificationRequirements: ["证券公司或具备债券承销能力的金融机构", "以官方招标文件为准"],
      publishedAt: "2026-01-21T00:00:00+08:00",
      discoveredAt: "2026-05-12T10:00:00+08:00",
      deadlineAt: "2026-02-12T09:00:00+08:00",
      openingAt: "2026-02-12T09:00:00+08:00",
      remainingHoursAtDiscovery: -2137,
      firstDiscoveryStage: "award",
      alertStatus: "miss_review",
      missReview: true,
      missReason: "V1首次入库时已到中标结果阶段，未在公告期建立提醒。"
    }
  ],
  findings: [
    {
      findingId: "finding-jinzi-corporate-bond-result-20260707",
      title: "陕西金资2026年公司债主承销商和联席主承销商项目结果线索",
      purchaser: "陕西金融资产管理股份有限公司",
      stage: "award",
      eligibilityStatus: "eligible",
      sourceQuality: "discovery_only",
      discoveredAt: "2026-07-07T08:20:00+08:00",
      publishedAt: "2026-07-02T00:00:00+08:00",
      deadlineAt: null,
      classification: "history",
      alertStatus: "miss_review",
      decision: "结果阶段首次发现，进入回源与漏检复盘，不进入新机会。",
      nextAction: "获取官方公告正文、项目编号、完整中标人、费率和服务期限。"
    },
    {
      findingId: "finding-icbc-it-excluded-20260709",
      title: "工商银行陕西省分行职业伤害保障信息系统建设开发服务",
      purchaser: "中国工商银行陕西省分行",
      stage: "announcement",
      eligibilityStatus: "excluded",
      sourceQuality: "authoritative",
      discoveredAt: "2026-07-09T08:20:00+08:00",
      publishedAt: "2026-07-09T00:00:00+08:00",
      deadlineAt: "2026-07-28T09:00:00+08:00",
      classification: "excluded",
      alertStatus: "none",
      decision: "信息系统开发服务，不符合证券公司资本市场服务适配口径。",
      nextAction: "保留排除审计，不进入机会区。"
    }
  ],
  scanRuns: [
    {
      tenderScanRunId: "tender-scan-import-20260710-morning",
      runMode: "v1_manual_import",
      startedAt: "2026-07-10T08:00:00+08:00",
      finishedAt: "2026-07-10T08:20:00+08:00",
      sourceScope: ["陕西招投标平台方向", "重点主体", "公开网页补漏"],
      candidateCount: 1,
      activeOpportunityCount: 0,
      resultFindingCount: 1,
      excludedCount: 0,
      status: "PASS_WITH_REVIEW",
      note: "未取得新的官方正文增量；沿用项目库，但没有把历史结果包装成新机会。"
    }
  ]
};

data.meta.schemaVersion = "0.5";
data.meta.note = "Phase 3招投标链路：当前真实活跃机会为0；历史结果和非证券采购分别进入漏检复盘与排除审计。60分钟自动化v3-60已启用，单站失败按来源健康状态降级。";
fs.writeFileSync(samplePath, `${JSON.stringify(data, null, 2)}\n`);
console.log(`Phase 3 tender monitor added: ${data.tenderMonitor.activeOpportunityEventIds.length} active, ${data.tenderMonitor.projects.length} history project, ${data.tenderMonitor.findings.length} findings.`);
