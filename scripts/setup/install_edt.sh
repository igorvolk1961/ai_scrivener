#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  printf '%s\n' "Run this script with sudo." >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
INSTALLER_DIR="${1:-$USER_HOME/.local/share/1c-edt-installer}"
INSTALLER="$INSTALLER_DIR/1ce-installer-cli"

if [[ ! -x "$INSTALLER" ]]; then
  printf '%s\n' "EDT installer not found: $INSTALLER" >&2
  exit 1
fi

exec "$INSTALLER" install --ignore-signature-warnings
