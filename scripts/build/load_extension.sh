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
PG_BASE=${PG_BASE:-ai_scrivener_fixed}
XML_DIR=${XML_DIR:-$REPO_ROOT/artifacts/extension-xml}
LOG=${LOG:-${TMPDIR:-/tmp}/kilo/load_extension.log}
FREE_FILE_BASE=${FREE_FILE_BASE:-0}
FREE_HELPER=$REPO_ROOT/scripts/run/free-file-base.sh

if [[ ! -f "$XML_DIR/Configuration.xml" ]]; then
  echo "Extension XML not found: $XML_DIR/Configuration.xml" >&2
  echo "Run scripts/build/export_extension.sh first." >&2
  exit 1
fi

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

PARKED=0
cleanup() {
  if [[ "$PARKED" -eq 1 ]]; then
    "$FREE_HELPER" restore || true
  fi
}
trap cleanup EXIT

mkdir -p "$(dirname -- "$LOG")"
rm -f "$LOG"

if [[ "$MODE" == "file" && "$FREE_FILE_BASE" == "1" ]]; then
  AIS_IB="$FILE_IB" "$FREE_HELPER" park
  PARKED=1
fi

AUTH_ARGS=(/N "$IB_USER")
if [[ -n "$IB_PASSWORD" ]]; then
  AUTH_ARGS+=(/P "$IB_PASSWORD")
fi

echo "Loading $EXT_NAME into $MODE base: $CONNECTION"

set +e
"$ONEC" DESIGNER "$CONNECTION" \
  "${AUTH_ARGS[@]}" \
  /LoadConfigFromFiles "$XML_DIR" \
  -Extension "$EXT_NAME" \
  -updateConfigDumpInfo \
  /UpdateDBCfg \
  /Out "$LOG" \
  /DisableStartupDialogs \
  /DisableStartupMessages
STATUS=$?
set -e

if [[ -s "$LOG" ]]; then
  cat "$LOG"
fi

if [[ $STATUS -ne 0 ]]; then
  echo "Extension load failed with exit code $STATUS" >&2
  exit "$STATUS"
fi

echo "Extension loaded successfully"
