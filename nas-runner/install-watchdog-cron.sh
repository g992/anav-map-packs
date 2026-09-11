#!/usr/bin/env bash
set -euo pipefail

NAS_HOME="${NAS_HOME:-/volume2/homes/G992}"
WATCHDOG="$NAS_HOME/anav-map-packs-builder/nas-runner/watchdog.sh"
CRONTAB_FILE="${CRONTAB_FILE:-/etc/crontab}"
MARKER="# anav-map-packs-watchdog"
SCHEDULE="${WATCHDOG_SCHEDULE:-5 9 * * *}"

if (( EUID != 0 )); then
  echo "Run this installer with sudo." >&2
  exit 1
fi

if [[ ! -x "$WATCHDOG" ]]; then
  echo "Watchdog is missing or not executable: $WATCHDOG" >&2
  exit 1
fi

if [[ ! -f "$CRONTAB_FILE" ]]; then
  echo "System crontab not found: $CRONTAB_FILE" >&2
  exit 1
fi

tmp=$(mktemp)
backup="$CRONTAB_FILE.anav-map-packs.$(date '+%Y%m%d%H%M%S').bak"
trap 'rm -f "$tmp"' EXIT

cp -p "$CRONTAB_FILE" "$backup"
awk -v marker="$MARKER" 'index($0, marker) == 0' "$CRONTAB_FILE" > "$tmp"
printf '%s\troot\t/bin/bash %s >/dev/null 2>&1\t%s\n' \
  "$SCHEDULE" "$WATCHDOG" "$MARKER" >> "$tmp"
cat "$tmp" > "$CRONTAB_FILE"
chmod 0644 "$CRONTAB_FILE"

# Synology's crond normally notices /etc/crontab changes. HUP makes the reload
# immediate without interrupting currently running scheduled tasks.
crond_pid=$(cat /run/crond.pid 2>/dev/null || /usr/bin/pidof crond 2>/dev/null || true)
if [[ -n "$crond_pid" ]]; then
  kill -HUP "${crond_pid%% *}" 2>/dev/null || true
fi

echo "Installed daily watchdog at 09:05 local time."
echo "Backup: $backup"
echo "Running the first check now..."
"$WATCHDOG"
