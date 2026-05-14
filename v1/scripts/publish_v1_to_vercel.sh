#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

cd "$repo_root"

echo "==> Refreshing V1 archive index"
python3 v1/scripts/generate_v1_previews.py
python3 v1/scripts/update_v1_index.py

echo "==> Validating Vercel config"
python3 -m json.tool vercel.json >/dev/null

echo "==> Current local changes"
git status --short

echo "==> Deploying static V1 archive to Vercel production"
npm_config_cache="$repo_root/.npm-cache" npx vercel --prod

echo
echo "Published:"
echo "https://shaanxi-capital-market-daily.vercel.app"
