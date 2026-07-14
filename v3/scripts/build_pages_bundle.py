#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DATA_FILES = (
    "config/listed-business-taxonomy.json",
    "config/tender-sources.json",
    "data/annual/2026.json",
    "data/backfill/coverage-2026.json",
    "data/listed/universe.json",
    "data/listed/workspace-2026.json",
    "data/ma-projects/latest.json",
    "data/pre-ipo/latest.json",
    "data/private-fund/snapshots/latest.json",
    "data/private-fund/workspace-2026.json",
    "data/relationships/latest.json",
    "data/runtime/event-store-summary.json",
    "data/sample/dashboard-2026-07-10.json",
    "data/tender/alerts/latest.json",
    "data/tender/scans/latest.json",
)


def copy_file(relative: str, output: Path) -> None:
    source = ROOT / relative
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages bundle for V3.")
    parser.add_argument("--output", default=str(ROOT / "dist/pages-v3"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for source in (ROOT / "site").iterdir():
        target = output / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    for relative in DATA_FILES:
        copy_file(relative, output)

    replacements = {
        "../data/": "./data/",
        "../config/": "./config/",
        "../../soe-radar/": "../soe-radar/",
        "本地原型": "GitHub 正式预览",
    }
    for relative in ("index.html", "app.js", "styles.css"):
        path = output / relative
        content = path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")

    for path in output.rglob("*.json"):
        content = path.read_text(encoding="utf-8").replace('"../data/', '"./data/')
        path.write_text(content, encoding="utf-8")

    release_id = hashlib.sha256((output / "app.js").read_bytes() + (output / "styles.css").read_bytes()).hexdigest()[:12]
    index_path = output / "index.html"
    index_content = index_path.read_text(encoding="utf-8")
    index_content = index_content.replace("./styles.css", f"./styles.css?v={release_id}")
    index_content = index_content.replace("./app.js", f"./app.js?v={release_id}")
    index_content = index_content.replace("./assets/lucide.min.js", f"./assets/lucide.min.js?v={release_id}")
    index_path.write_text(index_content, encoding="utf-8")

    compatibility_dir = output / "site"
    compatibility_dir.mkdir()
    (compatibility_dir / "index.html").write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url=../">
  <title>陕西资本市场情报 V3</title>
  <script>window.location.replace(`../${window.location.search}${window.location.hash}`);</script>
</head>
<body><a href="../">打开陕西资本市场情报 V3</a></body>
</html>
""",
        encoding="utf-8",
    )

    dashboard = json.loads((output / "data/sample/dashboard-2026-07-10.json").read_text(encoding="utf-8"))
    manifest = {
        "product": "Shaanxi Capital Market Intelligence V3",
        "releaseId": release_id,
        "schemaVersion": dashboard["meta"]["schemaVersion"],
        "dataAsOf": dashboard["meta"]["asOf"],
        "publishedFiles": len([path for path in output.rglob("*") if path.is_file()]),
    }
    (output / "release.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / ".nojekyll").touch()
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
