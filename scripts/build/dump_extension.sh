#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

MODE=${1:-server}
ONEC=${ONEC:-/opt/1cv8/x86_64/8.3.27.2342/1cv8}
EXT_NAME=${EXT_NAME:-ai_scrivener}
IB_USER=${IB_USER:-Администратор}
FILE_IB=${FILE_IB:-/home/igorvolk/1C/ai_scrivener_docmng}
PG_SERVER=${PG_SERVER:-localhost:1541}
PG_BASE=${PG_BASE:-ai_scrivener}
OUTPUT_DIR=${OUTPUT_DIR:-$REPO_ROOT/artifacts/base-extension-xml}
LOG=${LOG:-${TMPDIR:-/tmp}/kilo/dump_extension.log}

case "$MODE" in
  file)
    CONNECTION="/F$FILE_IB"
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

set +e
"$ONEC" DESIGNER "$CONNECTION" \
  /N "$IB_USER" \
  /DumpConfigToFiles "$OUTPUT_DIR" \
  -Extension "$EXT_NAME" \
  /Out "$LOG" \
  /DisableStartupDialogs
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
