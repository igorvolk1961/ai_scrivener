#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

MODE=${1:-server}
ONEC=${ONEC:-/opt/1cv8/x86_64/8.3.27.2342/1cv8}
EXT_NAME=${EXT_NAME:-ai_scrivener}
IB_USER=${IB_USER:-Администратор}
IB_PASSWORD=${IB_PASSWORD:-}
FILE_IB=${FILE_IB:-/home/igorvolk/1C/ai_scrivener_docmng}
PG_SERVER=${PG_SERVER:-localhost:1541}
PG_BASE=${PG_BASE:-ai_scrivener}
OUTPUT_DIR=${OUTPUT_DIR:-$REPO_ROOT/artifacts/base-extension-xml}
LOG=${LOG:-${TMPDIR:-/tmp}/kilo/dump_extension.log}

if [[ ! -x "$ONEC" ]]; then
  echo "1C executable not found: $ONEC (set ONEC=/path/to/1cv8)" >&2
  exit 1
fi

case "$MODE" in
  file)
    CONNECTION="/F$FILE_IB"
    if [[ ! -d "$FILE_IB" ]]; then
      echo "File infobase not found: $FILE_IB" >&2
      exit 1
    fi
    ;;
  server)
    CONNECTION="/S$PG_SERVER/$PG_BASE"
    ;;
  *)
    echo "Usage: $0 [file|server]" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname -- "$OUTPUT_DIR")"
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
mkdir -p "$(dirname -- "$LOG")"
rm -f "$LOG"

AUTH_ARGS=(/N "$IB_USER")
if [[ -n "$IB_PASSWORD" ]]; then
  AUTH_ARGS+=(/P "$IB_PASSWORD")
fi

set +e
"$ONEC" DESIGNER "$CONNECTION" \
  "${AUTH_ARGS[@]}" \
  /DumpConfigToFiles "$OUTPUT_DIR" \
  -Extension "$EXT_NAME" \
  /Out "$LOG" \
  /DisableStartupDialogs \
  /DisableStartupMessages
STATUS=$?
set -e

if [[ -s "$LOG" ]]; then
  cat "$LOG"
fi

if [[ $STATUS -ne 0 ]]; then
  echo "Extension dump failed with exit code $STATUS" >&2
  exit "$STATUS"
fi

echo "Extension XML dumped to $OUTPUT_DIR"
