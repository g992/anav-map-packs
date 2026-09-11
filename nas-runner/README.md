# NAS build runner

This container runs the repository's OpenFreeMap build jobs on `G992-NAS` while
keeping all persistent state below `/volume2/homes/G992`.

Host directories:

- `anav-map-packs-runner`: GitHub runner registration and job workspace;
- `anav-map-packs-data`: verified OpenFreeMap source archive and transient packs.

The container does not mount the Docker socket or the rest of the home
directory. It drops Linux capabilities and runs as UID 1026/GID 100.

## First registration

Create a one-time repository runner token, copy `.env.example` to `.env`, and
replace the placeholder. The token expires after one hour and is only needed
for the first registration.

Start the container on Synology:

```bash
cd /volume2/homes/G992/anav-map-packs-builder/nas-runner
sudo /usr/local/bin/docker-compose --env-file .env -f compose.yaml up -d --build
sudo /usr/local/bin/docker logs --tail 100 anav-map-packs-runner
```

After the runner appears online in the repository settings, clear the token
value in `.env`. Persistent registration is stored in
`$HOME/anav-map-packs-runner`.

Do not add the self-hosted label to workflows triggered by `pull_request`.
GitHub recommends against attaching self-hosted runners to public repositories;
this container reduces host exposure but does not remove repository-token risk.

## Optional isolated IKEv2 route

`compose.vpn.yaml` adds a strongSwan IKEv2 client and places only the Actions
runner in its network namespace. It does not change the NAS host route. Store
`ipsec.conf`, `ipsec.secrets` and the provider CA certificate outside the Git
checkout in `${VPN_CONFIG_DIR}`. Start the overlay with:

```bash
sudo /usr/local/bin/docker-compose \
  --env-file .env \
  -f compose.yaml \
  -f compose.vpn.yaml \
  up -d --build
```

The VPN container is granted `NET_ADMIN`, which strongSwan requires to install
IPsec policies. The runner keeps its existing non-root user, dropped Linux
capabilities and restricted mounts. It starts only after the VPN reports an
established `adguard` connection.

## Isolated AdGuard VPN CLI route

AdGuard documents that its IKEv2 profile may be unavailable in Russia and
other filtered networks. `compose.adguard.yaml` uses the official AdGuard VPN
CLI release and its HTTPS-like protocol instead. Only the runner shares the VPN
container's network namespace; the NAS host route remains unchanged.

Create the persistent authentication directory and start the overlay:

```bash
mkdir -p /volume2/homes/G992/anav-map-packs-adguard-state
chmod 700 /volume2/homes/G992/anav-map-packs-adguard-state
sudo /usr/local/bin/docker-compose \
  --env-file .env \
  -f compose.yaml \
  -f compose.adguard.yaml \
  up -d --build
```

On its first start the VPN waits for account authentication. Run the login
helper, follow the displayed browser link, then restart the stack:

```bash
sudo /usr/local/bin/docker exec -it anav-map-packs-vpn anav-adguard-login
sudo /usr/local/bin/docker-compose \
  --env-file .env \
  -f compose.yaml \
  -f compose.adguard.yaml \
  restart
```

The state directory contains the AdGuard account token. Keep it private and do
not add it to Git. The router-specific IKEv2 username and password are not used
by AdGuard VPN CLI.

## Daily watchdog

`watchdog.sh` verifies that both containers are running, the VPN is healthy,
the runner route uses `tun0`, GitHub is reachable through the tunnel, and the
runner has an active Actions session. It restarts the VPN and runner only when
one of those checks fails. Logs are written to
`/volume2/homes/G992/anav-map-packs-watchdog.log` and rotate at 1 MiB.

Install the root cron entry once on the NAS:

```bash
cd /volume2/homes/G992/anav-map-packs-builder/nas-runner
sudo ./install-watchdog-cron.sh
```

The check runs daily at 09:05 NAS local time, shortly before the Monday 09:17
weekly build. The installer is idempotent and keeps a timestamped backup of
`/etc/crontab`. Run an immediate check or force a clean reconnect with:

```bash
sudo ./watchdog.sh
sudo ./watchdog.sh --force
```
