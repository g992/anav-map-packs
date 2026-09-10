#!/bin/sh
set -eu

state_dir="/root/.local/share/adguardvpn-cli"
auth_marker="${state_dir}/.anav-authenticated"

mkdir -p "$state_dir"
chmod 700 "$state_dir"

adguardvpn-cli login
touch "$auth_marker"

echo "Authentication saved. Restart the VPN service to connect."
