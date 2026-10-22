#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=/home/igorvolk/PycharmProjects/ai_scrivener
RAGENT=/opt/1cv8/x86_64/8.3.27.2342/ragent
DATA_DIR=/home/igorvolk/1C/1cv8-server-data
COMPOSE_FILE=deploy/docker-compose.1c-db.yml

cd "$PROJECT_DIR"

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
