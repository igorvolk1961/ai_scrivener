#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  exit 0
fi

printf '%s\n' "1C binary artifacts must not be committed:" >&2
printf '  %s\n' "$@" >&2
printf '%s\n' "Store .cfe/.cf/.dt outside Git (artifacts/releases)." >&2
exit 1
