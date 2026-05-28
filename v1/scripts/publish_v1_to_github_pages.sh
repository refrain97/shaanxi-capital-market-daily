#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
date_value="$(date +%F)"
pages_url="https://refrain97.github.io/shaanxi-capital-market-daily/v1/"
worktree_dir="${TMPDIR:-/tmp}/shaanxi-capital-market-daily-gh-pages"
verify_attempts="${GITHUB_PAGES_VERIFY_ATTEMPTS:-60}"
verify_sleep="${GITHUB_PAGES_VERIFY_SLEEP:-10}"

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

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  PYTHON_BIN="$repo_root/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

wait_for_pages_build() {
  "$PYTHON_BIN" - "$verify_attempts" "$verify_sleep" <<'PY'
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

attempts = int(sys.argv[1])
sleep_seconds = int(sys.argv[2])

def credential_token() -> str:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    proc = subprocess.run(
        ["git", "credential-osxkeychain", "get"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        return ""
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""

token = credential_token()
if not token:
    print("GitHub Pages API token unavailable; skip build-status wait.")
    raise SystemExit(0)

url = "https://api.github.com/repos/refrain97/shaanxi-capital-market-daily/pages/builds/latest"
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "shaanxi-capital-market-daily-publisher",
}
for attempt in range(1, attempts + 1):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"GitHub Pages status check failed: HTTP {exc.code} {detail[:300]}")
        raise SystemExit(0)
    except urllib.error.URLError as exc:
        print(f"GitHub Pages status check failed: {exc}")
        raise SystemExit(0)

    status = str(page.get("status") or "")
    commit = str(page.get("commit") or "")
    short_commit = commit[:7] if commit else "unknown"
    print(f"GitHub Pages build status: {status or 'unknown'} commit={short_commit} attempt {attempt}/{attempts}")
    if status == "built":
        raise SystemExit(0)
    if status in {"errored", "error", "failed"}:
        raise SystemExit(2)
    time.sleep(sleep_seconds)

raise SystemExit(1)
PY
}

verify_live_pages() {
  expected="${date_value} 更新"
  for ((attempt=1; attempt<=verify_attempts; attempt++)); do
    page_html="$(curl -fsSL -H "Cache-Control: no-cache" "${pages_url}?verify=${date_value}-${attempt}")"
    if grep -Fq "$expected" <<<"$page_html"; then
      echo "GitHub Pages verified: $pages_url contains '$expected'"
      return 0
    fi
    echo "waiting for GitHub Pages CDN... attempt $attempt/$verify_attempts"
    sleep "$verify_sleep"
  done

  echo "GitHub Pages verification failed: $pages_url did not contain '$expected'" >&2
  return 1
}

echo "==> Packaging static site for GitHub Pages"
"$PYTHON_BIN" v1/scripts/package_portable_project.py

if [[ "${GITHUB_PAGES_PUBLISH_MODE:-git}" == "api" ]]; then
  echo "==> Publishing gh-pages via GitHub API"
  "$PYTHON_BIN" v1/scripts/publish_v1_to_github_pages_api.py \
    --dist "$repo_root/dist/shaanxi-capital-market-daily" \
    --date "$date_value"
  echo "==> Waiting for GitHub Pages build"
  set +e
  wait_for_pages_build
  pages_status=$?
  set -e
  if [[ "$pages_status" == "2" ]]; then
    echo "GitHub Pages build failed." >&2
    exit 1
  elif [[ "$pages_status" != "0" ]]; then
    echo "GitHub Pages build status did not settle before live verification; checking CDN anyway."
  fi
  echo "==> Verifying live GitHub Pages date"
  verify_live_pages
  exit $?
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

echo "==> Waiting for GitHub Pages build"
set +e
wait_for_pages_build
pages_status=$?
set -e
if [[ "$pages_status" == "2" ]]; then
  echo "GitHub Pages build failed." >&2
  exit 1
elif [[ "$pages_status" != "0" ]]; then
  echo "GitHub Pages build status did not settle before live verification; checking CDN anyway."
fi

echo "==> Verifying live GitHub Pages date"
verify_live_pages
