#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
date_value="$(date +%F)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      date_value="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$repo_root"

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  PYTHON_BIN="$repo_root/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

echo "==> Refreshing V1 archive index"
"$PYTHON_BIN" v1/scripts/generate_v1_previews.py --date "$date_value"
"$PYTHON_BIN" v1/scripts/update_v1_index.py
"$PYTHON_BIN" v1/scripts/inject_analytics.py
"$PYTHON_BIN" v1/scripts/validate_v1_outputs.py --date "$date_value"
"$PYTHON_BIN" v1/scripts/check_v1_responsive.py

echo "==> Validating Vercel config"
"$PYTHON_BIN" -m json.tool vercel.json >/dev/null

echo "==> Current local changes"
git status --short

echo "==> Deploying static V1 archive to Vercel production"
if command -v vercel >/dev/null 2>&1; then
  vercel_cmd=(vercel)
elif command -v npx >/dev/null 2>&1; then
  vercel_cmd=(npx vercel)
elif [[ -x "$repo_root/.vercel-cli/node_modules/.bin/vercel" ]]; then
  vercel_cmd=("$repo_root/.vercel-cli/node_modules/.bin/vercel")
else
  echo "Vercel CLI not found. Install it with npm, or run: node .npm-bootstrap/package/bin/npm-cli.js install --prefix .vercel-cli vercel" >&2
  exit 1
fi
npm_config_cache="$repo_root/.npm-cache" "${vercel_cmd[@]}" --prod --yes

echo "==> Deploying static V1 archive to GitHub Pages"
bash v1/scripts/publish_v1_to_github_pages.sh --date "$date_value"

echo
echo "Published:"
echo "GitHub Pages: https://refrain97.github.io/shaanxi-capital-market-daily/v1/"
echo "Vercel: https://shaanxi-capital-market-daily.vercel.app"
