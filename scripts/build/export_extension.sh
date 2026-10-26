#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

EDT_HOME=${EDT_HOME:-/home/igorvolk/.local/share/1C/1cedtstart/installations/1C_EDT 2026.1 (2)/1cedt}
EDT_CLI=${EDT_CLI:-$EDT_HOME/1cedtcli}
EDT_DATA=${EDT_DATA:-/home/igorvolk/.edt-workspace/docmng_base}
EDT_PROJECT=${EDT_PROJECT:-ai_scrivener_build}
OUTPUT_DIR=${OUTPUT_DIR:-$REPO_ROOT/artifacts/extension-xml}
WORKSPACE_PROJECT=${WORKSPACE_PROJECT:-$EDT_DATA/$EDT_PROJECT}

if [[ ! -f "$REPO_ROOT/src/Configuration/Configuration.mdo" ]]; then
  echo "Extension source not found: $REPO_ROOT/src/Configuration/Configuration.mdo" >&2
  exit 1
fi

if [[ ! -d "$WORKSPACE_PROJECT" ]]; then
  echo "EDT project not found: $WORKSPACE_PROJECT" >&2
  echo "Create/open the extension project in EDT or set EDT_PROJECT/EDT_DATA." >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required to synchronize $REPO_ROOT/src to $WORKSPACE_PROJECT/src" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$OUTPUT_DIR")"
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

rsync -a --delete "$REPO_ROOT/src/" "$WORKSPACE_PROJECT/src/"

# Required: export reads EDT's indexed project model, not the filesystem
# directly. Without a build first, changes to some object kinds (confirmed:
# Rights.rights) silently don't make it into the exported XML even though
# the source file on disk is correct - a build step is the fix.
"$EDT_CLI" \
  -data "$EDT_DATA" \
  -timeout 600 \
  -vmargs -Xmx8g \
  -command build -y true "$EDT_PROJECT"

"$EDT_CLI" \
  -data "$EDT_DATA" \
  -timeout 600 \
  -vmargs -Xmx8g \
  -command export \
  --project-name "$EDT_PROJECT" \
  --configuration-files "$OUTPUT_DIR"

echo "Extension XML exported to $OUTPUT_DIR"
