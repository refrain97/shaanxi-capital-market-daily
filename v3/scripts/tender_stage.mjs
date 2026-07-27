const stripHtml = (value = "") => value
  .replace(/<[^>]*>/g, "")
  .replace(/&nbsp;|&#160;/g, " ")
  .replace(/\s+/g, " ")
  .trim();

export function inferStage(record) {
  const title = stripHtml(record.title);
  const category = stripHtml(record.categoryname || "");
  const infer = (text) => {
    if (/终止|流标|废标/.test(text)) return "terminated";
    if (/候选人/.test(text)) return "candidate";
    if (/(中标|成交)结果|中标公示|成交公示/.test(text)) return "award";
    if (/更正|变更|澄清|答疑/.test(text)) return "change";
    if (/招标|采购|遴选|选聘|征集|比选|资格预审/.test(text)) return "announcement";
    return null;
  };

  // Search APIs can return a stale or conflicting category name. The bulletin
  // title contains the publication's own lifecycle label, so it wins.
  return infer(title) || infer(category) || "pending";
}
