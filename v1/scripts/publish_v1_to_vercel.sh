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

echo "==> Refreshing V1 archive index"
python3 v1/scripts/generate_v1_previews.py
python3 v1/scripts/update_v1_index.py
python3 v1/scripts/inject_analytics.py
python3 v1/scripts/validate_v1_outputs.py --date "$date_value"
python3 v1/scripts/check_v1_responsive.py

echo "==> Validating Vercel config"
python3 -m json.tool vercel.json >/dev/null

echo "==> Current local changes"
git status --short

echo "==> Deploying static V1 archive to Vercel production"
npm_config_cache="$repo_root/.npm-cache" npx vercel --prod

echo "==> Deploying static V1 archive to GitHub Pages"
bash v1/scripts/publish_v1_to_github_pages.sh --date "$date_value"

echo
echo "Published:"
echo "GitHub Pages: https://refrain97.github.io/shaanxi-capital-market-daily/v1/"
echo "Vercel: https://shaanxi-capital-market-daily.vercel.app"
