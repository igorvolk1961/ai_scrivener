#!/usr/bin/env bash
set -euo pipefail

ONEC=${ONEC:-/opt/1cv8/x86_64/8.3.27.2342/1cv8}
IB=${AIS_IB:-${IB:-/home/igorvolk/1C/ai_scrivener_stage2}}
IB_USER=${AIS_IB_USER:-${IB_USER:-Администратор}}
IB_PASSWORD=${AIS_IB_PASSWORD:-${IB_PASSWORD:-}}
PG_SERVER=${PG_SERVER:-localhost:1541}
PG_BASE=${PG_BASE:-ai_scrivener_fixed}
LOG_DIR=${AIS_LOG_DIR:-${TMPDIR:-/tmp}/kilo}
LOGIN=${2:-}

usage() {
  printf '%s\n' "Usage: $0 [launcher|designer [login]|enterprise [login]|check|pg-enterprise [login]|pg-designer [login]|pg-check|pg-db]" >&2
  printf '%s\n' "  launcher      - окно запуска 1С" >&2
  printf '%s\n' "  designer      - Конфигуратор на файловой базе (без логина — окно входа)" >&2
  printf '%s\n' "  enterprise    - 1С:Предприятие на файловой базе (без логина — окно входа)" >&2
  printf '%s\n' "  check         - CheckConfig файловой базы (по умолчанию Администратор)" >&2
  printf '%s\n' "  pg-enterprise - 1С:Предприятие на серверной базе PostgreSQL" >&2
  printf '%s\n' "  pg-designer   - Конфигуратор на серверной базе PostgreSQL" >&2
  printf '%s\n' "  pg-check      - CheckConfig серверной базы PostgreSQL" >&2
  printf '%s\n' "  pg-db         - psql к базе 1С в Docker" >&2
  printf '%s\n' "" >&2
  printf '%s\n' "По умолчанию открывается ai_scrivener_stage2 (расширение активно)." >&2
  printf '%s\n' "Демо-база: IB=/home/igorvolk/1C/ai_scrivener_docmng." >&2
  printf '%s\n' "Переопределение через окружение: ONEC, IB (или AIS_IB), IB_USER, IB_PASSWORD, PG_BASE." >&2
}

if [[ ! -x "$ONEC" ]]; then
  echo "1C executable not found: $ONEC (set ONEC=/path/to/1cv8)" >&2
  exit 1
fi

AUTH_ARGS=()
if [[ -n "$LOGIN" ]]; then
  AUTH_ARGS=(/N "$LOGIN")
  if [[ -n "$IB_PASSWORD" ]]; then
    AUTH_ARGS+=(/P "$IB_PASSWORD")
  fi
fi

CHECK_AUTH_ARGS=(/N "${LOGIN:-$IB_USER}")
if [[ -n "$IB_PASSWORD" ]]; then
  CHECK_AUTH_ARGS+=(/P "$IB_PASSWORD")
fi

extension_active() {
  local ib=$1 ibcmd active
  ibcmd=$(dirname -- "$ONEC")/ibcmd
  [[ -x "$ibcmd" && -d "$ib" ]] || { echo unknown; return; }
  active=$(timeout 5 "$ibcmd" infobase config extension list \
    --db-path="$ib" --user="$IB_USER" </dev/null 2>/dev/null \
    | awk '/name/{name=$3} /active/{if(name=="\"ai_scrivener\""){print $3; exit}}' || true)
  echo "${active:-unknown}"
}

ensure_active_extension() {
  local active fallback=/home/igorvolk/1C/ai_scrivener_stage2
  active=$(extension_active "$IB")
  [[ "$active" == "yes" ]] && return 0
  if [[ "$IB" != "$fallback" && -d "$fallback" ]]; then
    if [[ "$active" == "no" ]]; then
      echo "WARNING: расширение ai_scrivener выключено в $IB." >&2
    else
      echo "WARNING: не удалось проверить расширение ai_scrivener в $IB." >&2
    fi
    echo "         Открываю $fallback, где расширение заведомо активно." >&2
    IB=$fallback
    return 0
  fi
  if [[ "$active" == "no" ]]; then
    echo "ERROR: расширение ai_scrivener выключено в $IB — раздел «ИИ-Помощник» (АИС_Сервис) будет скрыт." >&2
    echo "       Включите расширение в Конфигураторе или задайте IB=$fallback." >&2
    exit 1
  fi
  return 0
}

require_file_base() {
  if [[ ! -d "$IB" ]]; then
    echo "File infobase not found: $IB (set IB=/path/to/base)" >&2
    exit 1
  fi
}

case "${1:-launcher}" in
  launcher)
    exec "$ONEC"
    ;;
  designer)
    require_file_base
    ensure_active_extension
    exec "$ONEC" DESIGNER /F"$IB" "${AUTH_ARGS[@]}"
    ;;
  enterprise)
    require_file_base
    ensure_active_extension
    exec "$ONEC" ENTERPRISE /F"$IB" "${AUTH_ARGS[@]}"
    ;;
  check)
    require_file_base
    ensure_active_extension
    mkdir -p "$LOG_DIR"
    exec "$ONEC" DESIGNER /F"$IB" "${CHECK_AUTH_ARGS[@]}" \
      /CheckConfig /Out "$LOG_DIR/check.log" \
      /DisableStartupDialogs /DisableStartupMessages
    ;;
  pg-enterprise)
    exec "$ONEC" ENTERPRISE /S"$PG_SERVER/$PG_BASE" "${AUTH_ARGS[@]}"
    ;;
  pg-designer)
    exec "$ONEC" DESIGNER /S"$PG_SERVER/$PG_BASE" "${AUTH_ARGS[@]}"
    ;;
  pg-check)
    mkdir -p "$LOG_DIR"
    exec "$ONEC" DESIGNER /S"$PG_SERVER/$PG_BASE" "${CHECK_AUTH_ARGS[@]}" \
      /CheckConfig /Out "$LOG_DIR/check_pg.log" \
      /DisableStartupDialogs /DisableStartupMessages
    ;;
  pg-db)
    DOCKER_TTY=()
    if [[ -t 0 && -t 1 ]]; then
      DOCKER_TTY=(-it)
    else
      DOCKER_TTY=(-i)
    fi
    exec docker exec "${DOCKER_TTY[@]}" deploy-postgres-1 psql -U ai_scrivener -d ai_scrivener
    ;;
  *)
    usage
    exit 2
    ;;
esac
