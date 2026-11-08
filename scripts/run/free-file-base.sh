#!/usr/bin/env bash
set -euo pipefail

# Временно освобождает файловую базу, опубликованную через Apache.
#
# Apache-воркеры держат соединение с файловой базой и мешают
# /UpdateDBCfg и /LoadConfigFromFiles. Скрипт переключает default.vrd на
# «парковочную» базу и убивает воркеры, чтобы они переподключились к ней.
# После операции restore возвращает публикацию на исходную базу.
#
# Usage:
#   free-file-base.sh park
#   free-file-base.sh restore
#   free-file-base.sh status
#
# Environment:
#   AIS_IB / IB            - освобождаемая файловая база
#   AIS_PARK_IB            - база-заглушка для default.vrd
#   AIS_VRD                - путь к default.vrd
#   APACHE_WORKER_USER     - пользователь воркеров Apache (по умолчанию определяется)
#   AIS_STATE_DIR          - каталог состояния (по умолчанию /tmp/kilo)

IB=${AIS_IB:-${IB:-/home/igorvolk/1C/ai_scrivener_stage2}}
PARK_IB=${AIS_PARK_IB:-/home/igorvolk/1C/ai_scrivener_final}
VRD=${AIS_VRD:-/var/www/ai_scrivener/default.vrd}
STATE_DIR=${AIS_STATE_DIR:-${TMPDIR:-/tmp}/kilo}
STATE_FILE="$STATE_DIR/free-file-base.state"

usage() {
  printf '%s\n' "Usage: $0 [park|restore|status]" >&2
  printf '%s\n' "  park    - переключить публикацию на $PARK_IB и остановить воркеры" >&2
  printf '%s\n' "  restore - вернуть публикацию на $IB и остановить воркеры" >&2
  printf '%s\n' "  status  - показать текущее состояние" >&2
}

worker_user() {
  if [[ -n "${APACHE_WORKER_USER:-}" ]]; then
    printf '%s\n' "$APACHE_WORKER_USER"
    return
  fi
  ps -o user= -C apache2 2>/dev/null | awk '$1 != "root" {print $1; exit}'
}

kill_workers() {
  local user
  user=$(worker_user)
  if [[ -z "$user" ]]; then
    echo "Apache workers not found; nothing to stop." >&2
    return
  fi
  if [[ "$user" != "$(id -un)" && "$(id -u)" -ne 0 ]]; then
    echo "Apache workers run as '$user'; run this script as root or via sudo." >&2
    exit 1
  fi
  pkill -KILL -u "$user" -x apache2 2>/dev/null || true
  sleep 1
}

set_vrd_base() {
  local target=$1
  if [[ ! -f "$VRD" ]]; then
    echo "Publication file not found: $VRD" >&2
    return 1
  fi
  if [[ ! -w "$VRD" ]]; then
    echo "Publication file is not writable: $VRD" >&2
    return 1
  fi
  if ! python3 - "$VRD" "$target" <<'PY'
import re
import sys

path, target = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    text = handle.read()
pattern = r'ib="File=&quot;[^"]*&quot;;"'
if not re.search(pattern, text):
    sys.exit(2)
text = re.sub(pattern, lambda _match: f'ib="File=&quot;{target}&quot;;"', text)
with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
PY
  then
    echo "Failed to switch $VRD to $target" >&2
    return 1
  fi
  if ! grep -q "ib=\"File=&quot;${target}&quot;;\"" "$VRD"; then
    echo "Failed to verify publication switch: $VRD" >&2
    return 1
  fi
}

case "${1:-status}" in
  park)
    mkdir -p "$STATE_DIR"
    if [[ -f "$STATE_FILE" ]]; then
      echo "Base is already parked. Run '$0 restore' first." >&2
      exit 1
    fi
    if [[ -f "$VRD" ]]; then
      backup="$STATE_DIR/default.vrd.$(date +%s).bak"
      cp -a "$VRD" "$backup"
      printf '%s\n' "$backup" > "$STATE_FILE"
      if ! set_vrd_base "$PARK_IB"; then
        cp -a "$backup" "$VRD"
        rm -f "$STATE_FILE"
        echo "Publication switch failed; original .vrd restored." >&2
        exit 1
      fi
      echo "Publication switched to $PARK_IB (backup: $backup)"
    else
      echo "Publication file not found, skipping .vrd switch: $VRD"
      printf '%s\n' "" > "$STATE_FILE"
    fi
    kill_workers
    echo "File base released: $IB"
    ;;
  restore)
    if [[ ! -f "$STATE_FILE" ]]; then
      echo "Nothing to restore." >&2
      exit 0
    fi
    backup=$(cat "$STATE_FILE")
    if [[ -z "$backup" ]]; then
      echo "No .vrd backup to restore; skipping publication switch."
    elif [[ -f "$backup" ]]; then
      cp -a "$backup" "$VRD"
      echo "Publication restored from $backup"
    else
      set_vrd_base "$IB"
      echo "Publication restored to $IB"
    fi
    rm -f "$STATE_FILE"
    kill_workers
    echo "Publication is active again for $IB"
    ;;
  status)
    if [[ -f "$STATE_FILE" ]]; then
      echo "parked (state: $(cat "$STATE_FILE"))"
    else
      echo "active"
    fi
    if [[ -f "$VRD" ]]; then
      grep -o 'ib="[^"]*"' "$VRD" || true
    fi
    ;;
  *)
    usage
    exit 2
    ;;
esac
