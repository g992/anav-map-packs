FROM ubuntu:24.04

ARG RUNNER_VERSION=2.337.0
ARG RUNNER_SHA256=70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613
ARG RUNNER_UID=1026
ARG RUNNER_GID=100

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl gh git jq python3 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid "$RUNNER_UID" --gid "$RUNNER_GID" runner \
    && mkdir -p /opt/actions-runner-dist /runner /data \
    && curl --fail --location --retry 4 \
        --output /tmp/actions-runner.tar.gz \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
    && printf '%s  %s\n' "$RUNNER_SHA256" /tmp/actions-runner.tar.gz | sha256sum --check --status \
    && tar -xzf /tmp/actions-runner.tar.gz -C /opt/actions-runner-dist \
    && rm /tmp/actions-runner.tar.gz \
    && /opt/actions-runner-dist/bin/installdependencies.sh \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R runner:"$RUNNER_GID" /opt/actions-runner-dist /runner /data

COPY --chmod=755 nas-runner/entrypoint.sh /usr/local/bin/anav-runner-entrypoint

USER runner
WORKDIR /runner
ENTRYPOINT ["/usr/local/bin/anav-runner-entrypoint"]
