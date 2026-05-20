#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "analytics.json"

HEAD_START = "<!-- V1_ANALYTICS_HEAD_START -->"
HEAD_END = "<!-- V1_ANALYTICS_HEAD_END -->"
BODY_START = "<!-- V1_ANALYTICS_BODY_START -->"
BODY_END = "<!-- V1_ANALYTICS_BODY_END -->"


def load_config() -> dict:
    if not CONFIG.exists():
        config = {}
    else:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    website_id = os.environ.get("V1_UMAMI_WEBSITE_ID", "").strip()
    if website_id:
        config["enabled"] = True
        config["website_id"] = website_id
    return config


def build_head(config: dict) -> str:
    enabled = bool(config.get("enabled"))
    provider = config.get("provider", "umami")
    website_id = str(config.get("website_id", "")).strip()
    script_url = str(config.get("script_url", "")).strip()

    if provider != "umami" or not enabled or not website_id or website_id == "YOUR-UMAMI-WEBSITE-ID":
        return f"{HEAD_START}\n  <!-- Analytics disabled. Configure v1/config/analytics.json to enable Umami. -->\n  {HEAD_END}"

    domains = ",".join(str(item).strip() for item in config.get("track_domains", []) if str(item).strip())
    domains_attr = f' data-domains="{html.escape(domains, quote=True)}"' if domains else ""
    return (
        f"{HEAD_START}\n"
        f'  <script defer src="{html.escape(script_url, quote=True)}" '
        f'data-website-id="{html.escape(website_id, quote=True)}"{domains_attr}></script>\n'
        f"  {HEAD_END}"
    )


def build_body() -> str:
    return f"""{BODY_START}
  <script>
    (() => {{
      const analytics = {{
        track(eventName, properties = {{}}) {{
          if (!window.umami || typeof window.umami.track !== "function") return;
          window.umami.track(eventName, {{
            path: window.location.pathname,
            title: document.title,
            ...properties
          }});
        }}
      }};

      function cleanUrl(value) {{
        return String(value || "").split("?")[0].toLowerCase();
      }}

      function assetType(url) {{
        const clean = cleanUrl(url);
        if (clean.endsWith(".html")) return "html";
        if (clean.endsWith(".md")) return "markdown";
        if (clean.endsWith(".png")) return "png";
        if (clean.endsWith(".jpg") || clean.endsWith(".jpeg") || clean.endsWith(".webp")) return "image";
        if (clean.startsWith("#")) return "anchor";
        return "link";
      }}

      function channel(url) {{
        if (url.includes("上市公司")) return "listed";
        if (url.includes("证券私募")) return "private";
        if (url.includes("收并购")) return "ma";
        if (url.includes("金融招投标")) return "tender";
        return "site";
      }}

      document.addEventListener("click", (event) => {{
        const shareButton = event.target.closest("[data-share-url]");
        if (shareButton) {{
          const shareUrl = new URL(shareButton.dataset.shareUrl, window.location.href).toString();
          navigator.clipboard?.writeText(shareUrl);
          analytics.track("share_copy", {{
            report: shareButton.dataset.shareReport || "",
            target_url: shareUrl
          }});
          return;
        }}

        const filterButton = event.target.closest("[data-filter]");
        if (filterButton) {{
          analytics.track("filter_archive", {{
            filter: filterButton.dataset.filter || ""
          }});
          return;
        }}

        const link = event.target.closest("a[href]");
        if (!link) return;

        const href = link.getAttribute("href") || "";
        const type = assetType(href);
        if (type === "anchor") {{
          analytics.track("nav_click", {{
            label: link.textContent.trim() || link.getAttribute("aria-label") || "",
            target_url: href
          }});
          return;
        }}

        analytics.track(type === "html" ? "open_report" : "download_asset", {{
          channel: channel(href),
          asset_type: type,
          label: link.textContent.trim() || link.getAttribute("aria-label") || "",
          target_url: new URL(href, window.location.href).toString()
        }});
      }});

      const searchInput = document.querySelector("#searchInput");
      if (searchInput) {{
        searchInput.addEventListener("change", () => {{
          analytics.track("search_archive", {{
            keyword: searchInput.value.trim()
          }});
        }});
      }}
    }})();
  </script>
  {BODY_END}"""


def replace_block(content: str, start: str, end: str, replacement: str, before_pattern: str) -> str:
    pattern = re.compile(rf"\s*{re.escape(start)}.*?{re.escape(end)}", re.S)
    if pattern.search(content):
        return pattern.sub("\n" + replacement, content, count=1)
    return re.sub(before_pattern, replacement + r"\n\g<0>", content, count=1, flags=re.I)


def inject(path: Path, config: dict) -> bool:
    content = path.read_text(encoding="utf-8", errors="ignore")
    if "</head>" not in content.lower() or "</body>" not in content.lower():
        return False

    updated = replace_block(content, HEAD_START, HEAD_END, build_head(config), r"</head>")
    updated = replace_block(updated, BODY_START, BODY_END, build_body(), r"</body>")
    if updated == content:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def target_files(include_samples: bool) -> list[Path]:
    files = sorted(ROOT.rglob("*.html"))
    if include_samples:
        return files
    return [
        path for path in files
        if path.name != "analytics-dashboard-sample.html"
        and "tmp" not in path.relative_to(ROOT).parts
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject V1 analytics script into published HTML files.")
    parser.add_argument("--include-samples", action="store_true")
    args = parser.parse_args()

    config = load_config()
    changed = [path for path in target_files(args.include_samples) if inject(path, config)]
    state = "enabled" if config.get("enabled") else "disabled"
    print(f"Analytics injection complete: {len(changed)} HTML files updated, config {state}.")
    if not config.get("enabled"):
        print("Set v1/config/analytics.json enabled=true and website_id to start real tracking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
