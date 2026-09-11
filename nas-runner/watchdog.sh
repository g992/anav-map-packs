#!/usr/bin/env bash
set -uo pipefail

NAS_HOME="${NAS_HOME:-/volume2/homes/G992}"
COMPOSE_DIR="${COMPOSE_DIR:-$NAS_HOME/anav-map-packs-builder/nas-runner}"
RUNNER_STATE_DIR="${RUNNER_STATE_DIR:-$NAS_HOME/anav-map-packs-runner}"
LOG_FILE="${LOG_FILE:-$NAS_HOME/anav-map-packs-watchdog.log}"
LOCK_DIR="${LOCK_DIR:-/tmp/anav-map-packs-watchdog.lock}"
DOCKER_BIN="${DOCKER_BIN:-/usr/local/bin/docker}"
COMPOSE_BIN="${COMPOSE_BIN:-/usr/local/bin/docker-compose}"
VPN_CONTAINER="${VPN_CONTAINER:-anav-map-packs-vpn}"
RUNNER_CONTAINER="${RUNNER_CONTAINER:-anav-map-packs-runner}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-30}"
WAIT_SECONDS="${WAIT_SECONDS:-10}"
FORCE_RESTART=false

if [[ "${1:-}" == "--force" ]]; then
  FORCE_RESTART=true
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--force]" >&2
  exit 2
fi

rotate_log() {
  local size
  [[ -f "$LOG_FILE" ]] || return 0
  size=$(wc -c < "$LOG_FILE" 2>/dev/null || printf '0')
  if (( size > 1048576 )); then
    mv -f "$LOG_FILE" "$LOG_FILE.1"
  fi
}

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*" | tee -a "$LOG_FILE"
}

release_lock() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "watchdog is already running; skipping"
  exit 0
fi
trap release_lock EXIT INT TERM

rotate_log
touch "$LOG_FILE"
chmod 0644 "$LOG_FILE" 2>/dev/null || true

docker() {
  "$DOCKER_BIN" "$@"
}

container_exists() {
  docker inspect "$1" >/dev/null 2>&1
}

vpn_is_healthy() {
  local state
  state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$VPN_CONTAINER" 2>/dev/null) || return 1
  [[ "$state" == "healthy" ]]
}

runner_is_running() {
  [[ "$(docker inspect --format '{{.State.Status}}' "$RUNNER_CONTAINER" 2>/dev/null)" == "running" ]]
}

actions_endpoint() {
  local endpoint
  endpoint=$(
    grep -rhoE 'https://[[:alnum:].-]+\.actions\.githubusercontent\.com' \
      "$RUNNER_STATE_DIR"/_diag/Runner_*.log 2>/dev/null \
      | tail -n 1
  )
  printf '%s' "$endpoint"
}

runner_connectivity_ok() {
  local endpoint

  runner_is_running || return 1
  docker exec "$RUNNER_CONTAINER" sh -c \
    "ip -4 route get 1.1.1.1 | grep -Eq 'dev tun0([[:space:]]|$)'" \
    >/dev/null 2>&1 || return 1
  docker exec "$RUNNER_CONTAINER" curl -4 -sS -o /dev/null \
    --connect-timeout 10 --max-time 20 https://github.com/ \
    >/dev/null 2>&1 || return 1

  endpoint=$(actions_endpoint)
  if [[ -n "$endpoint" ]]; then
    # The root path normally returns 404. Curl still exits successfully when
    # DNS, TCP and TLS work, which is the connectivity signal we need here.
    docker exec "$RUNNER_CONTAINER" curl -4 -sS -o /dev/null \
      --connect-timeout 10 --max-time 20 "$endpoint/" \
      >/dev/null 2>&1 || return 1
  fi
}

stack_is_healthy() {
  vpn_is_healthy && runner_connectivity_ok
}

start_stack() {
  (
    cd "$COMPOSE_DIR" || exit 1
    "$COMPOSE_BIN" \
      --env-file .env \
      -f compose.yaml \
      -f compose.adguard.yaml \
      up -d --no-build
  )
}

wait_for_vpn() {
  local attempt
  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
    if vpn_is_healthy; then
      return 0
    fi
    sleep "$WAIT_SECONDS"
  done
  return 1
}

wait_for_runner() {
  local attempt
  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
    if runner_connectivity_ok; then
      return 0
    fi
    sleep "$WAIT_SECONDS"
  done
  return 1
}

log "starting daily check"

if [[ "$FORCE_RESTART" == false ]] && stack_is_healthy; then
  log "VPN and runner connectivity are healthy"
  exit 0
fi

if [[ "$FORCE_RESTART" == true ]]; then
  log "forced daily reconnect requested"
else
  log "health check failed; restarting VPN and runner"
fi

if ! container_exists "$VPN_CONTAINER" || ! container_exists "$RUNNER_CONTAINER"; then
  log "one or more containers are missing; recreating the stack"
  if ! start_stack >>"$LOG_FILE" 2>&1; then
    log "ERROR: docker-compose could not create the stack"
    exit 1
  fi
else
  if ! docker restart "$VPN_CONTAINER" >>"$LOG_FILE" 2>&1; then
    log "ERROR: could not restart $VPN_CONTAINER"
    exit 1
  fi
fi

if ! wait_for_vpn; then
  log "ERROR: $VPN_CONTAINER did not become healthy"
  exit 1
fi

if ! runner_is_running; then
  if ! start_stack >>"$LOG_FILE" 2>&1; then
    log "ERROR: docker-compose could not start $RUNNER_CONTAINER"
    exit 1
  fi
else
  if ! docker restart "$RUNNER_CONTAINER" >>"$LOG_FILE" 2>&1; then
    log "ERROR: could not restart $RUNNER_CONTAINER"
    exit 1
  fi
fi

if ! wait_for_runner; then
  log "ERROR: runner still cannot reach GitHub through the VPN"
  exit 1
fi

log "recovery complete; VPN and runner connectivity are healthy"
