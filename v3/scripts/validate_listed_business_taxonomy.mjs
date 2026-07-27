import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { classifyListedBusiness, listedBusinessTaxonomy, taxonomyTag } from "./listed_business_taxonomy.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dashboard = JSON.parse(fs.readFileSync(path.join(root, "data/sample/dashboard-2026-07-10.json"), "utf8"));
const errors = [];
const expectedCategories = ["资本运作", "股东服务", "激励与员工", "资金与财务", "治理关系", "风险沟通", "业绩与分红", "经营与产业"];
const expectedFocus = new Set(["定增/再融资", "可转债", "并购重组", "分拆上市", "股份回购", "减持", "增持", "质押冻结", "权益变动", "转让拍卖", "限售解禁", "股权激励", "员工持股", "授予归属", "行权", "回购注销", "现金管理", "董监高", "董秘证代", "财务负责人", "对外投资"]);
const categories = listedBusinessTaxonomy.categories.map((item) => item.name);
if (JSON.stringify(categories) !== JSON.stringify(expectedCategories)) errors.push("LST-BIZ-001: eight primary categories or order changed");
const allTags = listedBusinessTaxonomy.categories.flatMap((category) => category.tags.map((tag) => ({ ...tag, category: category.name })));
const actualFocus = new Set(allTags.filter((item) => item.businessPriority === "focus").map((item) => item.name));
if (actualFocus.size !== expectedFocus.size || [...expectedFocus].some((item) => !actualFocus.has(item))) errors.push("LST-BIZ-002: focus business set does not match confirmed 21 tags");
if (taxonomyTag("资本运作", "股份回购")?.businessPriority !== "focus") errors.push("LST-BIZ-003: share repurchase must be a focus capital operation tag");
if (taxonomyTag("激励与员工", "回购注销")?.businessPriority !== "focus") errors.push("LST-BIZ-004: repurchase cancellation must remain a focus incentive tag");
const fixtures = [
  ["关于以集中竞价方式回购公司股份的方案", "资本运作", "股份回购"],
  ["关于回购注销部分限制性股票的公告", "激励与员工", "回购注销"],
  ["关于股东减持股份计划的公告", "股东服务", "减持"],
  ["关于使用闲置自有资金进行现金管理", "资金与财务", "现金管理"],
  ["关于聘任董事会秘书及证券事务代表", "治理关系", "董秘证代"],
  ["关于对外投资设立全资子公司的公告", "经营与产业", "对外投资"]
];
for (const [text, category, tag] of fixtures) {
  const result = classifyListedBusiness(text);
  if (result?.rmCategory !== category || result?.name !== tag || result?.businessPriority !== "focus") errors.push(`LST-BIZ-005: fixture misclassified: ${text}`);
}
for (const item of dashboard.listedDaily.items) {
  const tag = taxonomyTag(item.rmCategory, item.rmSubcategory);
  if (!tag) errors.push(`LST-BIZ-006: ${item.dailyItemId} references unknown business tag`);
  if (tag && item.businessPriority !== tag.businessPriority) errors.push(`LST-BIZ-007: ${item.dailyItemId} priority does not match taxonomy`);
}

if (errors.length) {
  console.error(`Listed business taxonomy validation failed (${errors.length})`);
  errors.forEach((error) => console.error(`- ${error}`));
  process.exit(1);
}
console.log(`Listed business taxonomy validation passed: ${categories.length} primary categories, ${allTags.length} secondary tags, ${actualFocus.size} focus tags.`);
