#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  exit 0
fi

if ! command -v bsl-language-server >/dev/null 2>&1; then
  printf '%s\n' "bsl-language-server not found; skipping BSL lint. Install it for full checks: guides/development.md." >&2
  exit 0
fi

exec bsl-language-server analyze \
  --configuration .bsl-language-server.json \
  --source src \
  --reporter json
