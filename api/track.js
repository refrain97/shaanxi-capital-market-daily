const DEFAULT_WEBSITE_ID = "ff2a4678-af6a-4b80-a4ff-15d3a9a62ebd";
const DEFAULT_UMAMI_ENDPOINT = "https://cloud.umami.is/api/send";
const PUBLIC_HOST = "shaanxi-capital-market-daily.vercel.app";
const ALLOWED_HOSTS = new Set([
  PUBLIC_HOST,
  "refrain97.github.io",
  "shaanxi-capital-market-daily-fdbpxmrb3-daily-reports.vercel.app",
]);

function firstHeader(value) {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

function normalizePath(value) {
  const raw = String(value || "").trim();
  if (!raw) return "/v1/";

  if (raw.startsWith("/")) {
    return raw.startsWith("/v1/") ? raw : "/v1/";
  }

  try {
    const url = new URL(raw);
    if (!ALLOWED_HOSTS.has(url.hostname) || !url.pathname.startsWith("/v1/")) {
      return "/v1/";
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/v1/";
  }
}

function redirectLocation(path) {
  return encodeURI(path || "/v1/");
}

function assetType(pathname) {
  const clean = pathname.split("?")[0].split("#")[0].toLowerCase();
  if (clean.endsWith(".html")) return "html";
  if (clean.endsWith(".png")) return "png";
  if (clean.endsWith(".md")) return "markdown";
  if (clean.endsWith(".jpg") || clean.endsWith(".jpeg") || clean.endsWith(".webp")) return "image";
  return "page";
}

function inferChannel(pathname) {
  if (pathname.includes("上市公司")) return "listed";
  if (pathname.includes("证券私募")) return "private";
  if (pathname.includes("收并购")) return "ma";
  if (pathname.includes("金融招投标")) return "tender";
  return "site";
}

function eventName(query, type) {
  const explicit = String(query.event || "").trim();
  if (/^[a-zA-Z0-9_:-]{1,64}$/.test(explicit)) return explicit;
  return type === "html" || type === "page" ? "server_open_report" : "server_download_asset";
}

async function sendUmamiEvent(req, query, targetPath) {
  const website = process.env.V1_UMAMI_WEBSITE_ID || DEFAULT_WEBSITE_ID;
  if (!website || website === "YOUR-UMAMI-WEBSITE-ID") return;

  const type = assetType(targetPath);
  const channel = String(query.channel || inferChannel(targetPath));
  const source = String(query.source || "redirect");
  const report = String(query.report || "");
  const userAgent = firstHeader(req.headers["user-agent"]) || "Mozilla/5.0";
  const referrer = firstHeader(req.headers.referer);
  const endpoint = process.env.V1_UMAMI_ENDPOINT || DEFAULT_UMAMI_ENDPOINT;

  const payload = {
    type: "event",
    payload: {
      hostname: PUBLIC_HOST,
      language: firstHeader(req.headers["accept-language"]).split(",")[0] || "zh-CN",
      referrer,
      screen: String(query.screen || "unknown"),
      title: "V1 report redirect",
      url: targetPath.split("#")[0],
      website,
      name: eventName(query, type),
      data: {
        channel,
        asset_type: type,
        report,
        source,
        target_path: targetPath,
        server_tracked: true,
      },
    },
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1200);
  try {
    await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": userAgent,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch {
    // Never block the reader from opening the report because analytics failed.
  } finally {
    clearTimeout(timer);
  }
}

module.exports = async function track(req, res) {
  const query = req.query || {};
  const targetPath = normalizePath(query.u || query.url || query.to);
  await sendUmamiEvent(req, query, targetPath);

  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("X-Robots-Tag", "noindex");
  res.statusCode = 302;
  res.setHeader("Location", redirectLocation(targetPath));
  res.end();
};
