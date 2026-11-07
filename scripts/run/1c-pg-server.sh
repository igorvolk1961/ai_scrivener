#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/../.." && pwd)
RAGENT=${RAGENT:-/opt/1cv8/x86_64/8.3.27.2342/ragent}
DATA_DIR=${AIS_PG_DATA_DIR:-/home/igorvolk/1C/1cv8-server-data}
COMPOSE_FILE=${COMPOSE_FILE:-deploy/docker-compose.1c-db.yml}

cd "$PROJECT_DIR"

if [[ ! -x "$RAGENT" ]]; then
  echo "1C server agent not found: $RAGENT (set RAGENT=/path/to/ragent)" >&2
  exit 1
fi

if [[ "${1:-start}" == "stop" ]]; then
  pkill -f "ragent.*1cv8-server-data" || true
  docker compose -f "$COMPOSE_FILE" stop
  exit 0
fi

docker compose -f "$COMPOSE_FILE" up -d
mkdir -p "$DATA_DIR"

if pgrep -f "ragent.*1cv8-server-data" >/dev/null; then
  echo "1C server agent is already running."
  echo "Use ./scripts/run/1c.sh pg-enterprise"
  echo "To restart: $0 stop, then $0"
  exit 0
fi

exec "$RAGENT" \
  -d "$DATA_DIR" \
  -port 1540 \
  -regport 1541 \
  -range 1560:1591 \
  -seclev 0
