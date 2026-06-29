#!/usr/bin/env bash
set -euo pipefail

ROOT="${BIRDBOX_ROOT:-/home/pi/birdbox}"
CLIPS_DIR="${BIRDBOX_CLIPS_DIR:-$ROOT/clips}"
mkdir -p "$CLIPS_DIR"

timestamp="$(date +%Y-%m-%d_%H-%M-%S)"
out="$CLIPS_DIR/birdbox_${timestamp}.mp4"

rpicam-vid \
  -t 15000 \
  --nopreview \
  --autofocus-mode manual \
  --lens-position 7 \
  --width 1280 \
  --height 720 \
  --framerate 15 \
  --codec h264 \
  -o "$out"

echo "$out"
