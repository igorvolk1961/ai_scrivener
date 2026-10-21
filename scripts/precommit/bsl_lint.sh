#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  exit 0
fi

if ! command -v bsl-language-server >/dev/null 2>&1; then
  printf '%s\n' "bsl-language-server is required for BSL linting. See docs/development.md." >&2
  exit 1
fi

exec bsl-language-server analyze \
  --configuration .bsl-language-server.json \
  --source src \
  --reporter json
