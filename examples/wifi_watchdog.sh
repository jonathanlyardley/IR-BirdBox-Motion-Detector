#!/usr/bin/env bash
set -euo pipefail

# Optional soft recovery watchdog. It deliberately does not reboot the Pi.
TARGET="${BIRDBOX_WATCHDOG_TARGET:-8.8.8.8}"

if ping -c 1 -W 5 "$TARGET" >/dev/null 2>&1; then
  exit 0
fi

logger -t birdbox-wifi "Ping failed; restarting wlan0"
sudo ip link set wlan0 down || true
sleep 5
sudo ip link set wlan0 up || true
sleep 15

if ping -c 1 -W 5 "$TARGET" >/dev/null 2>&1; then
  exit 0
fi

logger -t birdbox-wifi "Ping still failing; restarting wpa_supplicant"
sudo systemctl restart wpa_supplicant || true
