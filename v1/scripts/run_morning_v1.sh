#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
date_value="$(date +%F)"
start_date_value=""
finalize="0"

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  PYTHON_BIN="$repo_root/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      date_value="$2"
      shift 2
      ;;
    --start-date)
      start_date_value="$2"
      shift 2
      ;;
    --finalize)
      finalize="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$repo_root"

if [[ -z "$start_date_value" ]]; then
  start_date_value="$("$PYTHON_BIN" - "$date_value" <<'PY'
from datetime import date, timedelta
import sys

day = date.fromisoformat(sys.argv[1])
cursor = day - timedelta(days=1)
while cursor.weekday() >= 5:
    cursor -= timedelta(days=1)
print(cursor.isoformat())
PY
)"
fi

echo "V1 Shaanxi Capital Market Dynamics date: $date_value"
echo "Report retrieval window: $start_date_value -> $date_value"
echo
echo "0) Network and deployment preflight"
"$PYTHON_BIN" v1/scripts/preflight_v1_network.py --date "$date_value" --write-log || {
  echo "error V1 preflight failed; stop before producing or publishing an incomplete daily report" >&2
  exit 1
}
echo
echo "1) Data scripts that can run directly"

listed_dir="v1/陕西省上市公司日报v1"
listed_data="$listed_dir/data/cninfo-shaanxi-announcements-$date_value.json"
listed_needs_fetch="1"
if [[ -f "$listed_data" ]] && "$PYTHON_BIN" - "$listed_data" "$start_date_value" "$date_value" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_start = sys.argv[2]
expected_end = sys.argv[3]
data = json.loads(path.read_text(encoding="utf-8"))
summary = data.get("_summary", {})
error_count = int(summary.get("errorCount") or 0)
company_count = int(summary.get("companyUniverseCount") or 0)
if (
    summary.get("startDate") == expected_start
    and summary.get("endDate") == expected_end
    and error_count == 0
    and not (company_count and error_count >= company_count)
):
    raise SystemExit(0)
raise SystemExit(1)
PY
then
  listed_needs_fetch="0"
fi

if [[ "$listed_needs_fetch" == "0" ]]; then
  echo "ok listed data: $listed_data"
else
  echo "run listed CNINFO fetch ($start_date_value -> $date_value)"
  (
    cd "$listed_dir"
    "$PYTHON_BIN" scripts/fetch_cninfo_shaanxi_announcements.py \
      --start-date "$start_date_value" \
      --end-date "$date_value" \
      --output "data/cninfo-shaanxi-announcements-$date_value.json"
  ) || {
    echo "error listed CNINFO fetch failed; stop before producing an incomplete daily report" >&2
    exit 1
  }
fi

private_dir="v1/陕西省证券私募日报v1"
private_data="$private_dir/data/security-private-fund-daily-$date_value.json"
private_html="$private_dir/outputs/security-private-fund-daily-$date_value-publish.html"
if [[ -f "$private_data" ]]; then
  echo "ok private data: $private_data"
else
  echo "run AMAC private-fund data script"
  "$PYTHON_BIN" "$private_dir/scripts/amac_security_private_daily.py" --date "$date_value" --sleep 0.3 || {
    echo "error AMAC private-fund data script failed; stop before producing an incomplete daily report" >&2
    exit 1
  }
fi
if [[ -f "$private_data" && ! -f "$private_html" ]]; then
  echo "render private-fund publish HTML"
  "$PYTHON_BIN" "$private_dir/scripts/render_security_private_publish.py" --date "$date_value"
fi

echo
echo "2) SOP-driven channels"
echo "listed/private PNG, M&A case update, and finance tender report may still require Codex to read SOP, judge increments, write copy, and render images."
echo "If M&A or finance tender has no content change, render today's carry-forward image with v1/scripts/render_observation_cards.py before finalize."
echo "Runbook: v1/docs/MORNING_RUNBOOK.md"

echo
echo "3) Current output check"
"$PYTHON_BIN" - "$date_value" <<'PY'
from datetime import date
from pathlib import Path
import sys

root = Path.cwd()
day = date.fromisoformat(sys.argv[1])
zh = f"{day.year}年{day.month}月{day.day}日"
items = [
    ("listed markdown", root / f"v1/陕西省上市公司日报v1/outputs/shaanxi-listed-company-morning-{day:%Y-%m-%d}.md"),
    ("listed curated json", root / f"v1/陕西省上市公司日报v1/data/curated/listed-official-{day:%Y-%m-%d}.json"),
    ("listed html", root / f"v1/陕西省上市公司日报v1/outputs/shaanxi-listed-company-morning-{day:%Y-%m-%d}-publish.html"),
    ("listed png", root / f"v1/陕西省上市公司日报v1/outputs/{zh}陕西上市公司早报.png"),
    ("private markdown", root / f"v1/陕西省证券私募日报v1/outputs/security-private-fund-daily-{day:%Y-%m-%d}.md"),
    ("private html", root / f"v1/陕西省证券私募日报v1/outputs/security-private-fund-daily-{day:%Y-%m-%d}-publish.html"),
    ("private png", root / f"v1/陕西省证券私募日报v1/outputs/{zh}证券私募行业动态日报.png"),
    ("ma markdown", root / f"v1/陕西省收并购日报v1/outputs/shaanxi-ma-daily-{day:%Y-%m-%d}.md"),
    ("ma png", root / f"v1/陕西省收并购日报v1/outputs/{zh}陕西辖区收并购事件详细案例看板.png"),
    ("tender markdown", root / f"v1/陕西省金融招投标项目v1/outputs/shaanxi-finance-tender-projects-{day:%Y-%m-%d}.md"),
    ("tender html", root / f"v1/陕西省金融招投标项目v1/outputs/shaanxi-finance-tender-projects-{day:%Y-%m-%d}-publish.html"),
    ("tender png", root / f"v1/陕西省金融招投标项目v1/outputs/shaanxi-finance-tender-projects-{day:%Y-%m-%d}.png"),
]
for label, path in items:
    print(("ok      " if path.exists() else "missing ") + f"{label}: {path.relative_to(root)}")
PY

if [[ "$finalize" == "1" ]]; then
  echo
  echo "4) Finalize: upload ima and publish web"
  bash v1/scripts/upload_daily_ima.sh --date "$date_value"
  bash v1/scripts/publish_v1_to_vercel.sh --date "$date_value"
else
  echo
  echo "Finalize after all outputs are ready:"
  echo "bash v1/scripts/run_morning_v1.sh --date $date_value --finalize"
fi
