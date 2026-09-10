#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f /runner/.runner ]]; then
  : "${REPO_URL:?REPO_URL is required for initial registration}"
  : "${RUNNER_TOKEN:?RUNNER_TOKEN is required for initial registration}"
  cp -a /opt/actions-runner-dist/. /runner/
  /runner/config.sh \
    --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "${RUNNER_NAME:-G992-NAS-ofm}" \
    --labels "${RUNNER_LABELS:-ofm-builder}" \
    --work /runner/_work \
    --unattended \
    --replace
fi

exec /runner/run.sh
