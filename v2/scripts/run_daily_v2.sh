#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
RUN_DATE=$(TZ=Asia/Shanghai date +%F)
SLOT=morning
PUBLISH=0
EXPECTED_START=""
MAX_START_LAG_MINUTES=60
RECOVERY_OF=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --date)
      RUN_DATE=$2
      shift 2
      ;;
    --slot)
      SLOT=$2
      shift 2
      ;;
    --publish)
      PUBLISH=1
      shift
      ;;
    --expected-start)
      EXPECTED_START=$2
      shift 2
      ;;
    --max-start-lag-minutes)
      MAX_START_LAG_MINUTES=$2
      shift 2
      ;;
    --recovery-of)
      RECOVERY_OF=$2
      shift 2
      ;;
    *)
      echo "未知参数：$1" >&2
      exit 2
      ;;
  esac
done

case "$SLOT" in
  morning|midday|closing) ;;
  *)
    echo "无效时点：$SLOT（仅支持 morning、midday、closing）" >&2
    exit 2
    ;;
esac

if [ -z "$EXPECTED_START" ]; then
  case "$SLOT" in
    morning) EXPECTED_START="05:30" ;;
    midday) EXPECTED_START="12:00" ;;
    closing) EXPECTED_START="17:00" ;;
  esac
fi

cd "$ROOT_DIR"

PYTHON_BIN=python3
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

set -- "$PYTHON_BIN" v2/scripts/run_v2_pipeline.py \
  --date "$RUN_DATE" --slot "$SLOT" \
  --expected-start "$EXPECTED_START" \
  --max-start-lag-minutes "$MAX_START_LAG_MINUTES"
if [ "$PUBLISH" -eq 1 ]; then
  set -- "$@" --publish
fi
if [ -n "$RECOVERY_OF" ]; then
  set -- "$@" --recovery-of "$RECOVERY_OF"
fi
"$@"

# V2 owns data, pages, daily images and IMA delivery. This wrapper performs no
# legacy-version hand-off.
