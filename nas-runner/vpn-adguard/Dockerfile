FROM ubuntu:24.04

ARG ADGUARD_VPN_VERSION=1.7.12
ARG ADGUARD_VPN_SHA256=a706933c87ec88eec8578cce96d2b91c385e083cf738a806e69b3bcd877fb88c

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl iproute2 iptables procps \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --retry 4 \
        --output /tmp/adguardvpn-cli.tar.gz \
        "https://github.com/AdguardTeam/AdGuardVPNCLI/releases/download/v${ADGUARD_VPN_VERSION}-release/adguardvpn-cli-${ADGUARD_VPN_VERSION}-linux-x86_64.tar.gz" \
    && printf '%s  %s\n' "$ADGUARD_VPN_SHA256" /tmp/adguardvpn-cli.tar.gz | sha256sum --check --status \
    && mkdir -p /opt/adguardvpn-cli \
    && tar -xzf /tmp/adguardvpn-cli.tar.gz -C /opt/adguardvpn-cli --strip-components=1 \
    && ln -s /opt/adguardvpn-cli/adguardvpn-cli /usr/local/bin/adguardvpn-cli \
    && rm /tmp/adguardvpn-cli.tar.gz

COPY --chmod=755 nas-runner/vpn-adguard/entrypoint.sh /usr/local/bin/anav-adguard-entrypoint
COPY --chmod=755 nas-runner/vpn-adguard/login.sh /usr/local/bin/anav-adguard-login

ENTRYPOINT ["/usr/local/bin/anav-adguard-entrypoint"]
