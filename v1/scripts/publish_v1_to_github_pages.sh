#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
date_value="$(date +%F)"
pages_url="https://refrain97.github.io/shaanxi-capital-market-daily/v1/"
worktree_dir="${TMPDIR:-/tmp}/shaanxi-capital-market-daily-gh-pages"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      date_value="$2"
      shift 2
      ;;
    --url)
      pages_url="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "$repo_root"

echo "==> Packaging static site for GitHub Pages"
python3 v1/scripts/package_portable_project.py

if [[ "${GITHUB_PAGES_PUBLISH_MODE:-git}" == "api" ]]; then
  echo "==> Publishing gh-pages via GitHub API"
  python3 v1/scripts/publish_v1_to_github_pages_api.py \
    --dist "$repo_root/dist/shaanxi-capital-market-daily" \
    --date "$date_value"
  echo "==> Verifying live GitHub Pages date"
  expected="${date_value} 更新"
  for attempt in {1..12}; do
    page_html="$(curl -fsSL -H "Cache-Control: no-cache" "${pages_url}?verify=${date_value}-${attempt}")"
    if grep -Fq "$expected" <<<"$page_html"; then
      echo "GitHub Pages verified: $pages_url contains '$expected'"
      exit 0
    fi
    echo "waiting for GitHub Pages CDN... attempt $attempt/12"
    sleep 10
  done
  echo "GitHub Pages verification failed: $pages_url did not contain '$expected'" >&2
  exit 1
fi

echo "==> Preparing gh-pages worktree"
if git worktree list --porcelain | grep -Fqx "worktree $worktree_dir"; then
  git worktree remove --force "$worktree_dir"
fi
rm -rf "$worktree_dir"
git worktree add --detach --no-checkout "$worktree_dir" origin/gh-pages
git -C "$worktree_dir" read-tree --empty

echo "==> Syncing dist/ to gh-pages"
rsync -a --delete --exclude=".git" "$repo_root/dist/shaanxi-capital-market-daily/" "$worktree_dir/"
touch "$worktree_dir/.nojekyll"

git -C "$worktree_dir" add -A
new_tree="$(git -C "$worktree_dir" write-tree)"
old_tree="$(git -C "$worktree_dir" rev-parse HEAD^{tree})"
if [[ "$new_tree" == "$old_tree" ]]; then
  echo "gh-pages already matches packaged site."
else
  git -C "$worktree_dir" commit -m "Deploy ${date_value} reports to GitHub Pages"
  git -C "$worktree_dir" push origin HEAD:gh-pages
fi

echo "==> Cleaning gh-pages worktree"
git worktree remove "$worktree_dir"

echo "==> Verifying live GitHub Pages date"
expected="${date_value} 更新"
for attempt in {1..12}; do
  page_html="$(curl -fsSL -H "Cache-Control: no-cache" "${pages_url}?verify=${date_value}-${attempt}")"
  if grep -Fq "$expected" <<<"$page_html"; then
    echo "GitHub Pages verified: $pages_url contains '$expected'"
    exit 0
  fi
  echo "waiting for GitHub Pages CDN... attempt $attempt/12"
  sleep 10
done

echo "GitHub Pages verification failed: $pages_url did not contain '$expected'" >&2
exit 1
