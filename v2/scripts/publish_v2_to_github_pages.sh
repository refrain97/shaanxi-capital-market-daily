#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
RUN_DATE=$(TZ=Asia/Shanghai date +%F)
SLOT=morning
SKIP_BUILD=0
ARCHIVE_STAGE=""
LIVE_ROOT="https://refrain97.github.io/shaanxi-capital-market-daily"

# Only the formal V2 runner may invoke this publisher. This prevents a page or
# image from bypassing the five-channel readiness gate merely because it looks
# complete in a browser.
if [ "${V2_PUBLISH_AUTHORIZED:-}" != "1" ]; then
  echo "拒绝直接发布：请通过 v2/scripts/run_daily_v2.sh --publish 的正式流水线运行。" >&2
  exit 2
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --date)
      RUN_DATE=$2
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --slot)
      SLOT=$2
      shift 2
      ;;
    --archive-stage)
      ARCHIVE_STAGE=$2
      shift 2
      ;;
    *)
      echo "未知参数：$1" >&2
      exit 2
      ;;
  esac
done

if [ -n "$ARCHIVE_STAGE" ] && [ ! -d "$ARCHIVE_STAGE" ]; then
  echo "日图暂存目录不存在：$ARCHIVE_STAGE" >&2
  exit 2
fi

cd "$ROOT_DIR"
if [ "$SKIP_BUILD" -eq 0 ]; then
  sh v2/scripts/run_daily_v2.sh --date "$RUN_DATE" --slot "$SLOT"
fi
python3 v2/scripts/validate_v2.py --date "$RUN_DATE" --slot "$SLOT" --skip-tests

BUILD_VERSION=$(python3 -c 'import json; print(json.load(open("v2/data/production-data.json"))["build"]["version"])')
TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/v2-pages.XXXXXX")
WORKTREE="$TEMP_ROOT/gh-pages"
RESULT_FILE="$ROOT_DIR/v2/data/deployment-verification.json"
WORKTREE_ADDED=0

cleanup() {
  if [ "$WORKTREE_ADDED" -eq 1 ]; then
    git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
  # TEMP_ROOT is created by mktemp above and is never a user-supplied path.
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT INT TERM

git fetch origin gh-pages
REMOTE_SHA=$(git rev-parse refs/remotes/origin/gh-pages)
git worktree add --detach "$WORKTREE" refs/remotes/origin/gh-pages >/dev/null
WORKTREE_ADDED=1
mkdir -p "$WORKTREE/v2"

# Runtime-only allowlist. Source, test and documentation directories are never
# copied into the publish set.
for file in index.html listed.html private.html ma.html tender.html soe.html; do
  install -m 0644 "$ROOT_DIR/v2/$file" "$WORKTREE/v2/$file"
done
for dir in assets; do
  mkdir -p "$WORKTREE/v2/$dir"
  rsync -a --delete "$ROOT_DIR/v2/$dir/" "$WORKTREE/v2/$dir/"
done
mkdir -p "$WORKTREE/v2/data"
for file in production-data.json build-version.json daily-image-archive.json; do
  install -m 0644 "$ROOT_DIR/v2/data/$file" "$WORKTREE/v2/data/$file"
done
if [ -n "$ARCHIVE_STAGE" ]; then
  mkdir -p "$WORKTREE/v2/archive/daily"
  rsync -a "$ARCHIVE_STAGE/" "$WORKTREE/v2/archive/daily/"
fi
git -C "$WORKTREE" rm -f --ignore-unmatch v2/watchlist.html >/dev/null 2>&1 || true
git -C "$WORKTREE" rm -rf --ignore-unmatch \
  v2/images v2/share v2/data/share-images.json >/dev/null 2>&1 || true

if git -C "$WORKTREE" status --porcelain -- v2 | grep -Eq 'v2/(scripts|tests|docs|陕西省上市公司日报v2)'; then
  echo "发布清单越界，已拒绝发布。" >&2
  exit 1
fi
git -C "$WORKTREE" add -- \
  v2/index.html v2/listed.html v2/private.html v2/ma.html v2/tender.html v2/soe.html \
  v2/assets v2/data/production-data.json v2/data/build-version.json v2/data/daily-image-archive.json
if [ -d "$WORKTREE/v2/archive/daily" ]; then
  git -C "$WORKTREE" add -- v2/archive/daily
fi
if git -C "$WORKTREE" diff --cached --quiet; then
  echo "V2 线上内容已是当前构建，无需推送。"
else
  git -C "$WORKTREE" -c user.name="Codex V2 Publisher" -c user.email="codex-v2@users.noreply.github.com" \
    commit -m "Deploy V2 ${RUN_DATE} (${BUILD_VERSION})" >/dev/null
  git -C "$WORKTREE" push \
    --force-with-lease="refs/heads/gh-pages:$REMOTE_SHA" \
    origin HEAD:refs/heads/gh-pages
fi

V2_HTTP=""
V2_BODY="$TEMP_ROOT/v2-live.html"
V2_DATA="$TEMP_ROOT/v2-live-data.json"
ATTEMPT=0
while [ "$ATTEMPT" -lt 18 ]; do
  ATTEMPT=$((ATTEMPT + 1))
  V2_HTTP=$(curl -L -sS -H 'Cache-Control: no-cache' -o "$V2_BODY" -w '%{http_code}' "$LIVE_ROOT/v2/?v=$BUILD_VERSION" || true)
  if [ "$V2_HTTP" = "200" ] && grep -q "陕西资本市场日报 V2" "$V2_BODY" && grep -q "$BUILD_VERSION" "$V2_BODY"; then
    V2_DATA_HTTP=$(curl -L -sS -H 'Cache-Control: no-cache' -o "$V2_DATA" -w '%{http_code}' "$LIVE_ROOT/v2/data/production-data.json?v=$BUILD_VERSION" || true)
    if [ "$V2_DATA_HTTP" = "200" ] && python3 - "$V2_DATA" "$RUN_DATE" "$BUILD_VERSION" <<'PY'
import json
import sys

path, expected_date, expected_version = sys.argv[1:]
data = json.load(open(path, encoding="utf-8"))
if data.get("asOf") != expected_date:
    raise SystemExit(1)
if data.get("build", {}).get("version") != expected_version:
    raise SystemExit(1)
PY
    then
      break
    fi
  fi
  sleep 10
done
if [ "$V2_HTTP" != "200" ] || ! grep -q "$BUILD_VERSION" "$V2_BODY"; then
  echo "V2 已推送，但 Pages 尚未确认日期 $RUN_DATE 和构建版本 $BUILD_VERSION。" >&2
  exit 1
fi

# A daily image archive is only considered published after every staged PNG is
# reachable online and byte-identical to its staging file.  IMA is deliberately
# downstream of this proof.
ARCHIVE_CONFIRMED=true
ARCHIVE_COUNT=0
if [ -n "$ARCHIVE_STAGE" ]; then
  ARCHIVE_ATTEMPT=0
  while [ "$ARCHIVE_ATTEMPT" -lt 18 ]; do
    ARCHIVE_ATTEMPT=$((ARCHIVE_ATTEMPT + 1))
    ARCHIVE_CONFIRMED=true
    ARCHIVE_COUNT=0
    while IFS= read -r IMAGE_FILE; do
      ARCHIVE_COUNT=$((ARCHIVE_COUNT + 1))
      RELATIVE_IMAGE=${IMAGE_FILE#"$ARCHIVE_STAGE"/}
      REMOTE_IMAGE="$TEMP_ROOT/archive-$ARCHIVE_COUNT.png"
      IMAGE_HTTP=$(curl -L -sS -H 'Cache-Control: no-cache' -o "$REMOTE_IMAGE" -w '%{http_code}' "$LIVE_ROOT/v2/archive/daily/$RELATIVE_IMAGE?v=$BUILD_VERSION" || true)
      if [ "$IMAGE_HTTP" != "200" ] || [ "$(shasum -a 256 "$IMAGE_FILE" | awk '{print $1}')" != "$(shasum -a 256 "$REMOTE_IMAGE" | awk '{print $1}')" ]; then
        ARCHIVE_CONFIRMED=false
        break
      fi
    done <<EOF
$(find "$ARCHIVE_STAGE" -type f -name '*.png' | sort)
EOF
    if [ "$ARCHIVE_CONFIRMED" = "true" ]; then
      break
    fi
    sleep 10
  done
  if [ "$ARCHIVE_CONFIRMED" != "true" ]; then
    echo "V2 日图归档线上确认失败。" >&2
    exit 1
  fi
fi

python3 - "$RESULT_FILE" "$RUN_DATE" "$BUILD_VERSION" "$V2_HTTP" "$ARCHIVE_CONFIRMED" "$ARCHIVE_COUNT" <<'PY'
import json
import sys
from pathlib import Path

path, as_of, version, v2_http, archive_confirmed, archive_count = sys.argv[1:]
Path(path).write_text(json.dumps({
    "asOf": as_of,
    "buildVersion": version,
    "v2": {
        "url": "https://refrain97.github.io/shaanxi-capital-market-daily/v2/",
        "http": int(v2_http),
        "confirmed": True,
    },
    "dailyImageArchive": {
        "confirmed": archive_confirmed == "true",
        "imageCount": int(archive_count),
    },
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
cat "$RESULT_FILE"
