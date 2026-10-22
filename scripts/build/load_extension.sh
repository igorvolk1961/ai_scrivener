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
XML_DIR=${XML_DIR:-$REPO_ROOT/artifacts/extension-xml}
LOG=${LOG:-${TMPDIR:-/tmp}/kilo/load_extension.log}

if [[ ! -f "$XML_DIR/Configuration.xml" ]]; then
  echo "Extension XML not found: $XML_DIR/Configuration.xml" >&2
  echo "Run scripts/build/export_extension.sh first." >&2
  exit 1
fi

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

mkdir -p "$(dirname -- "$LOG")"
rm -f "$LOG"

echo "Loading $EXT_NAME into $MODE base: $CONNECTION"

set +e
"$ONEC" DESIGNER "$CONNECTION" \
  /N "$IB_USER" \
  /LoadConfigFromFiles "$XML_DIR" \
  -Extension "$EXT_NAME" \
  -updateConfigDumpInfo \
  /UpdateDBCfg \
  /Out "$LOG" \
  /DisableStartupDialogs
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
