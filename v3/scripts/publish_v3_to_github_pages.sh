#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
bundle_dir="$repo_root/v3/dist/pages-v3"
worktree_dir="${TMPDIR:-/tmp}/shaanxi-capital-market-daily-v3-gh-pages"
pages_url="https://refrain97.github.io/shaanxi-capital-market-daily/v3/"

cd "$repo_root"
python3 v3/scripts/build_pages_bundle.py --output "$bundle_dir"
release_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["releaseId"])' "$bundle_dir/release.json")"

git fetch origin gh-pages --quiet
old_commit="$(git rev-parse origin/gh-pages)"
git worktree prune
if git worktree list --porcelain | grep -Fqx "worktree $worktree_dir"; then
  git worktree remove --force "$worktree_dir"
fi
rm -rf "$worktree_dir"
git worktree add --detach "$worktree_dir" origin/gh-pages

rm -rf "$worktree_dir/v3"
mkdir -p "$worktree_dir/v3"
rsync -a --exclude=".git" "$bundle_dir/" "$worktree_dir/v3/"
touch "$worktree_dir/.nojekyll"

git -C "$worktree_dir" add -A -- v3 .nojekyll
if git -C "$worktree_dir" diff --cached --quiet; then
  echo "V3 GitHub Pages already matches the bundle."
else
  git -C "$worktree_dir" commit -m "Deploy V3 intelligence dashboard"
  deploy_commit="$(git -C "$worktree_dir" rev-parse HEAD)"
  git push --force-with-lease="refs/heads/gh-pages:$old_commit" origin "$deploy_commit:refs/heads/gh-pages"
fi

git worktree remove "$worktree_dir"

for attempt in $(seq 1 60); do
  release="$(curl -fsSL -H 'Cache-Control: no-cache' "${pages_url}release.json?verify=$attempt" 2>/dev/null || true)"
  page="$(curl -fsSL -H 'Cache-Control: no-cache' "${pages_url}?verify=$attempt" 2>/dev/null || true)"
  compatibility="$(curl -fsSL -H 'Cache-Control: no-cache' "${pages_url}site/?verify=$attempt" 2>/dev/null || true)"
  if grep -Fq 'Shaanxi Capital Market Intelligence V3' <<<"$release" \
    && grep -Fq "$release_id" <<<"$release" \
    && grep -Fq '陕西资本市场每日观察' <<<"$page" \
    && grep -Fq 'window.location.replace' <<<"$compatibility"; then
    echo "GitHub Pages verified: $pages_url"
    exit 0
  fi
  sleep 5
done

echo "GitHub Pages verification timed out: $pages_url" >&2
exit 1
