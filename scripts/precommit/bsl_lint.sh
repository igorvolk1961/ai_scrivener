#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  exit 0
fi

if ! command -v bsl-language-server >/dev/null 2>&1; then
  printf '%s\n' "bsl-language-server not found; skipping BSL lint. Install it for full checks: guides/development.md." >&2
  exit 0
fi

# BSL LS is JVM-based. Without a cap it can consume many GB and trigger the
# system OOM killer on workstations. Keep the local run predictable; override
# with BSL_LINT_JAVA_OPTS when a larger heap is really needed.
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-${BSL_LINT_JAVA_OPTS:--Xmx2g -XX:ActiveProcessorCount=4}}"

# --workspaceDir src is important: with the repository root as workspace the
# analyzer also walks .kilo/worktrees/* and analyzes duplicate BSL sources.
exec bsl-language-server analyze \
  --configuration .bsl-language-server.json \
  --srcDir src \
  --workspaceDir src \
  --reporter json
