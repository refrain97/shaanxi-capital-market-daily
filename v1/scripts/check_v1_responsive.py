#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
INDEX = ROOT / "index.html"
OUT_DIR = REPO_ROOT / "output" / "playwright"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

VIEWPORTS = (
    ("desktop", 1366, 1100),
    ("tablet", 820, 1100),
    ("mobile", 390, 1200),
)


METRIC_SCRIPT = """
<script>
window.addEventListener("load", () => {
  const doc = document.documentElement;
  const latest = document.querySelector("#latest");
  const lead = document.querySelector(".lead-report");
  const image = document.querySelector(".lead-image");
  const rect = (node) => {
    if (!node) return null;
    const r = node.getBoundingClientRect();
    return { left: r.left, right: r.right, width: r.width };
  };
  const metrics = {
    viewport: window.innerWidth,
    scrollWidth: doc.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    latest: rect(latest),
    lead: rect(lead),
    image: rect(image)
  };
  document.body.innerHTML = "<pre id=\\"v1-responsive-metrics\\">" +
    JSON.stringify(metrics) +
    "</pre>";
});
</script>
"""


def run_chrome(args: list[str]) -> str:
    if not CHROME.exists():
        raise SystemExit(f"Chrome not found: {CHROME}")
    result = subprocess.run(
        [str(CHROME), "--headless", "--disable-gpu", "--hide-scrollbars", *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout


def screenshot(name: str, width: int, height: int) -> None:
    out = OUT_DIR / f"v1-index-{name}.png"
    run_chrome(
        [
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
            f"--screenshot={out}",
            str(INDEX),
        ]
    )


def metrics(name: str, width: int, height: int) -> dict[str, object]:
    html = INDEX.read_text(encoding="utf-8")
    instrumented = OUT_DIR / f"v1-index-{name}-metrics.html"
    instrumented.write_text(html.replace("</body>", METRIC_SCRIPT + "\n</body>"), encoding="utf-8")
    dom = run_chrome(
        [
            f"--window-size={width},{height}",
            "--virtual-time-budget=1000",
            "--dump-dom",
            str(instrumented),
        ]
    )
    match = re.search(r'<pre id="v1-responsive-metrics">(\{.*?\})</pre>', dom, re.S)
    if not match:
        raise SystemExit(f"Could not read responsive metrics for {name}")
    return json.loads(match.group(1))


def check_viewport(name: str, width: int, height: int) -> list[str]:
    screenshot(name, width, height)
    data = metrics(name, width, height)
    failures: list[str] = []
    actual_width = int(data["viewport"])
    scroll_width = max(int(data["scrollWidth"]), int(data["bodyScrollWidth"]))
    if scroll_width > actual_width + 2:
        failures.append(f"{name}: horizontal overflow {scroll_width}/{actual_width}")
    for label in ("latest", "lead", "image"):
        rect = data.get(label)
        if isinstance(rect, dict) and float(rect["right"]) > actual_width + 2:
            failures.append(f"{name}: {label} exceeds viewport ({rect['right']} > {actual_width})")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Check V1 index responsive layout with Chrome.")
    parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for viewport in VIEWPORTS:
        failures.extend(check_viewport(*viewport))
    if failures:
        print("check_v1_responsive failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("check_v1_responsive: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
