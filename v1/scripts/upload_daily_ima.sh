#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
config_path="$repo_root/v1/config/ima.json"
date_value="$(date +%F)"
force="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      date_value="$2"
      shift 2
      ;;
    --force)
      force="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$repo_root"

python3 - "$config_path" "$date_value" <<'PY' > /tmp/v1_ima_upload_plan.tsv
import json
import sys
from datetime import date
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
day = date.fromisoformat(sys.argv[2])
zh_date = f"{day.year}年{day.month}月{day.day}日"
values = {
    "date": day.isoformat(),
    "zh_date": zh_date,
}

print("#kb", config["defaultKnowledgeBaseId"], config["defaultKnowledgeBaseName"], sep="\t")
for item in config["dailyPngUploads"]:
    path = item["pathTemplate"].format(**values)
    name = item["nameTemplate"].format(**values)
    record = item["recordTemplate"].format(**values)
    print(
        item["channel"],
        item["label"],
        path,
        name,
        record,
        item.get("keyword", item["label"]),
        sep="\t",
    )
PY

kb_id=""
kb_name=""
uploaded=0
skipped=0
missing=0

while IFS=$'\t' read -r channel label file_path upload_name record_path keyword; do
  if [[ "$channel" == "#kb" ]]; then
    kb_id="$label"
    kb_name="$file_path"
    continue
  fi

  if [[ ! -f "$file_path" ]]; then
    echo "skip missing: $label -> $file_path"
    missing=$((missing + 1))
    continue
  fi

  echo "branding: $label -> $file_path"
  python3 v1/scripts/brand_v1_png.py "$file_path" >/dev/null

  if [[ "$force" != "1" && -f "$record_path" ]] && grep -q '"uploadStatus": "success"' "$record_path"; then
    echo "skip uploaded: $label -> $record_path"
    skipped=$((skipped + 1))
    continue
  fi

  echo "uploading: $label -> $upload_name"
  node v1/scripts/upload_ima_png.cjs \
    --file "$file_path" \
    --name "$upload_name" \
    --record "$record_path" \
    --kb "$kb_id" \
    --kbName "$kb_name" \
    --keyword "$keyword" \
    --local "$file_path" >/dev/null
  uploaded=$((uploaded + 1))
done < /tmp/v1_ima_upload_plan.tsv

rm -f /tmp/v1_ima_upload_plan.tsv

echo "IMA upload summary: uploaded=$uploaded skipped=$skipped missing=$missing"
