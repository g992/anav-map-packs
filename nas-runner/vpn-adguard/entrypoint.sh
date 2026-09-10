#!/bin/sh
set -eu

state_dir="/root/.local/share/adguardvpn-cli"
auth_marker="${state_dir}/.anav-authenticated"

mkdir -p "$state_dir"
chmod 700 "$state_dir"

if [ ! -f "$auth_marker" ]; then
    echo "AdGuard VPN login is required. Run:"
    echo "  docker exec -it anav-map-packs-vpn anav-adguard-login"
    exec tail -f /dev/null
fi

adguardvpn-cli config set-mode TUN
adguardvpn-cli config set-change-system-dns off
adguardvpn-cli config set-tun-routing-mode AUTO
adguardvpn-cli config set-use-quic "${ADGUARD_VPN_USE_QUIC:-off}"
adguardvpn-cli config set-show-hints off

exec adguardvpn-cli connect \
    --no-fork \
    --yes \
    --ipv4only \
    --location "${ADGUARD_VPN_LOCATION:-Netherlands}"
