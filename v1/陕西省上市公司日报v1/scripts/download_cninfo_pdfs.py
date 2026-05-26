#!/usr/bin/env python3
"""Download CNINFO PDFs listed in the daily JSON and extract text."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader


BASE_URL = "https://static.cninfo.com.cn/"
SCRIPT_DIR = Path(__file__).resolve().parent
VERSION_DIR = SCRIPT_DIR.parent
DATA_DIR = VERSION_DIR / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and extract CNINFO announcement PDFs.")
    parser.add_argument("--date", required=True, help="Report date, YYYY-MM-DD.")
    parser.add_argument("--json", type=Path, help="CNINFO announcement JSON path.")
    parser.add_argument("--timeout", type=float, default=30)
    return parser.parse_args()


def safe_name(item: dict[str, Any]) -> str:
    code = str(item.get("secCode") or item.get("_matchedCompanyCode") or "unknown")
    announcement_id = str(item.get("announcementId") or "unknown")
    title = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(item.get("announcementTitle") or ""))[:60]
    return f"{code}_{announcement_id}_{title}".strip("_")


def item_date_key(payload: dict[str, Any]) -> str:
    summary = payload.get("_summary", {})
    return f"{summary.get('startDate')}~{summary.get('endDate')}"


def download(url: str, target: Path, timeout: float) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.cninfo.com.cn/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def main() -> int:
    args = parse_args()
    report_day = date.fromisoformat(args.date)
    json_path = args.json or DATA_DIR / f"cninfo-shaanxi-announcements-{report_day:%Y-%m-%d}.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    items = payload.get(item_date_key(payload), [])
    if not items:
        raise SystemExit(f"No announcement items found in {json_path}")

    pdf_dir = DATA_DIR / f"pdfs-{report_day:%Y-%m-%d}"
    text_dir = DATA_DIR / f"pdf-text-{report_day:%Y-%m-%d}"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    for index, item in enumerate(items, start=1):
        adjunct_url = str(item.get("adjunctUrl") or "")
        if not adjunct_url:
            errors.append(f"{index}: missing adjunctUrl")
            continue
        stem = safe_name(item)
        pdf_path = pdf_dir / f"{stem}.pdf"
        text_path = text_dir / f"{stem}.txt"
        url = adjunct_url if adjunct_url.startswith("http") else BASE_URL + adjunct_url
        try:
            if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                download(url, pdf_path, args.timeout)
            text = extract_text(pdf_path)
            text_path.write_text(text, encoding="utf-8")
            print(f"{index}/{len(items)} {pdf_path.name} text_chars={len(text)}")
        except Exception as exc:  # noqa: BLE001 - report all daily extraction failures.
            errors.append(f"{index}: {stem}: {exc!r}")

    if errors:
        print("PDF download/extraction errors:")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"download_cninfo_pdfs: ok pdf={len(list(pdf_dir.glob('*.pdf')))} text={len(list(text_dir.glob('*.txt')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
