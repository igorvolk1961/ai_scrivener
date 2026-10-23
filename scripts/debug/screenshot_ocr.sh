#!/usr/bin/env bash
set -euo pipefail

OUT=${OUT:-/tmp/kilo/1c-screen.png}
OCR_LANG=${OCR_LANG:-rus+eng}
WINDOW_ID=${WINDOW_ID:-}

usage() {
  printf '%s\n' "Usage: $0 [--list] [--window <id>]" >&2
  printf '%s\n' "  --list        show X11 windows and ids" >&2
  printf '%s\n' "  --window ID   capture a specific window" >&2
  printf '%s\n' "Default: find the first 1cv8 window and OCR it." >&2
}

if [[ "${1:-}" == "--list" ]]; then
  xwininfo -root -tree
  exit 0
fi

if [[ "${1:-}" == "--window" ]]; then
  WINDOW_ID=${2:-}
  if [[ -z "$WINDOW_ID" ]]; then
    usage
    exit 2
  fi
fi

if ! command -v gst-launch-1.0 >/dev/null 2>&1; then
  echo "gst-launch-1.0 is required" >&2
  exit 1
fi

if ! command -v tesseract >/dev/null 2>&1; then
  echo "tesseract is required" >&2
  exit 1
fi

if [[ -z "$WINDOW_ID" ]]; then
  WINDOW_ID=$(xwininfo -root -tree | grep '("1cv8" "1cv8")' | head -n 1 | awk '{print $1}')
fi

if [[ -z "$WINDOW_ID" ]]; then
  echo "1C window not found. Open 1C or pass --window <id>; use --list to see windows." >&2
  exit 1
fi

XID_DEC=$((WINDOW_ID))
mkdir -p "$(dirname -- "$OUT")"

gst-launch-1.0 -q ximagesrc xid="$XID_DEC" use-damage=false num-buffers=1 \
  ! videoconvert ! pngenc snapshot=true ! filesink location="$OUT"

tesseract "$OUT" stdout -l "$OCR_LANG" --psm 6
printf '\nScreenshot: %s\n' "$OUT" >&2
