#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PORT="${1:-4173}"

cd "${PROJECT_ROOT}"
printf 'V3 local dashboard: http://127.0.0.1:%s/v3/site/\n' "${PORT}"
python3 -m http.server "${PORT}" --bind 127.0.0.1
