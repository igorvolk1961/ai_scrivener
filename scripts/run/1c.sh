#!/usr/bin/env bash
set -euo pipefail

ONEC=/opt/1cv8/x86_64/8.3.27.2342/1cv8
IB=${AIS_IB:-/home/igorvolk/1C/ai_scrivener_docmng}
PG_SERVER=localhost:1541
PG_BASE=ai_scrivener
LOGIN=${2:-Администратор}

usage() {
  printf '%s\n' "Usage: $0 [launcher|designer [login]|enterprise [login]|check|pg-enterprise [login]|pg-designer [login]|pg-check|pg-db]" >&2
  printf '%s\n' "  launcher      - окно запуска 1С" >&2
  printf '%s\n' "  designer      - Конфигуратор на файловой демо-базе" >&2
  printf '%s\n' "  enterprise    - 1С:Предприятие на файловой демо-базе (логин по умолчанию: Администратор)" >&2
  printf '%s\n' "  check         - CheckConfig файловой демо-базы" >&2
  printf '%s\n' "  pg-enterprise - 1С:Предприятие на серверной базе PostgreSQL" >&2
  printf '%s\n' "  pg-designer   - Конфигуратор на серверной базе PostgreSQL" >&2
  printf '%s\n' "  pg-check      - CheckConfig серверной базы PostgreSQL" >&2
  printf '%s\n' "  pg-db         - psql к базе 1С в Docker" >&2
}

case "${1:-launcher}" in
  launcher)
    exec "$ONEC"
    ;;
  designer)
    exec "$ONEC" DESIGNER /F"$IB" /N "$LOGIN"
    ;;
  enterprise)
    exec "$ONEC" ENTERPRISE /F"$IB" /N "$LOGIN"
    ;;
  check)
    exec "$ONEC" DESIGNER /F"$IB" /N Администратор \
      /CheckConfig /Out /tmp/kilo/check.log /DisableStartupDialogs
    ;;
  pg-enterprise)
    exec "$ONEC" ENTERPRISE /S"$PG_SERVER/$PG_BASE" /N "$LOGIN"
    ;;
  pg-designer)
    exec "$ONEC" DESIGNER /S"$PG_SERVER/$PG_BASE" /N "$LOGIN"
    ;;
  pg-check)
    exec "$ONEC" DESIGNER /S"$PG_SERVER/$PG_BASE" /N Администратор \
      /CheckConfig /Out /tmp/kilo/check_pg.log /DisableStartupDialogs
    ;;
  pg-db)
    exec docker exec -it deploy-postgres-1 psql -U ai_scrivener -d ai_scrivener
    ;;
  *)
    usage
    exit 2
    ;;
esac
