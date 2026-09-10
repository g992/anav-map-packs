#!/usr/bin/env bash
set -euo pipefail

for path in /etc/ipsec.conf /etc/ipsec.secrets /etc/ipsec.d/cacerts/comodo.crt; do
  if [[ ! -s "$path" ]]; then
    echo "missing VPN configuration: $path" >&2
    exit 1
  fi
done

exec ipsec start --nofork
