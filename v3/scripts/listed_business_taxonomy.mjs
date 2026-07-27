import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const listedBusinessTaxonomy = JSON.parse(fs.readFileSync(path.join(root, "config/listed-business-taxonomy.json"), "utf8"));

const orderedTags = listedBusinessTaxonomy.categories.flatMap((category) => category.tags.map((tag) => ({ ...tag, rmCategory: category.name, targetObjects: category.targetObjects })));
const repurchaseCancellation = orderedTags.find((item) => item.name === "回购注销");
const shareRepurchase = orderedTags.find((item) => item.name === "股份回购");

export function classifyListedBusiness(text) {
  const value = String(text || "");
  if (repurchaseCancellation.keywords.some((keyword) => value.includes(keyword))) return repurchaseCancellation;
  if (shareRepurchase.keywords.some((keyword) => value.includes(keyword))) return shareRepurchase;
  return orderedTags.find((item) => item.keywords.some((keyword) => value.includes(keyword))) || null;
}

export function taxonomyTag(rmCategory, rmSubcategory) {
  return orderedTags.find((item) => item.rmCategory === rmCategory && item.name === rmSubcategory) || null;
}
