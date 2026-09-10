FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl iproute2 \
        strongswan strongswan-starter \
        libcharon-extra-plugins libstrongswan-extra-plugins \
    && rm -rf /var/lib/apt/lists/*

COPY --chmod=755 nas-runner/vpn/entrypoint.sh /usr/local/bin/anav-vpn-entrypoint

STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/anav-vpn-entrypoint"]
