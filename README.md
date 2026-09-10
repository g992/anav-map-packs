# ANAV regional map packs

Regional PMTiles snapshot automation derived from the public OpenFreeMap planet archive. GitHub Actions performs discovery, extraction, verification, publication and retention; no project-owned tile server is required.

## Published data

Each published release contains one `.pmtiles` file per catalog region, plus:

- `manifest.json` with stable IDs, names, sizes, SHA-256 checksums and download URLs;
- `catalog.json` describing the pinned boundary snapshot;
- `SHA256SUMS` for command-line verification.

The current catalog has 297 packs:

| Code | Area | Packs | Boundary level |
| --- | --- | ---: | --- |
| `ru` | Russia | 89 | ADM1 plus six explicitly mapped entries |
| `az` | Azerbaijan | 79 | ADM2 |
| `am` | Armenia | 11 | ADM1 |
| `by` | Belarus | 7 | ADM1 |
| `kz` | Kazakhstan | 16 | ADM1 |
| `kg` | Kyrgyzstan | 7 | ADM1 |
| `md` | Moldova | 37 | ADM1 |
| `tj` | Tajikistan | 5 | ADM1 |
| `tm` | Turkmenistan | 5 | ADM1 |
| `uz` | Uzbekistan | 14 | ADM1 |
| `ua` | Ukraine | 27 | ADM1 |

The source boundary snapshot is intentionally pinned so weekly builds cannot silently rename or move packs. It is a packaging catalog, not a statement about sovereignty. The six entries mapped into the Russian catalog are also retained in the Ukrainian source catalog, reflecting the conflicting classifications of the source systems. See [ISSUES.md](ISSUES.md) before changing this policy.

## Automation

`Publish weekly regional maps` is currently manual while the OpenFreeMap source-read blocker below is unresolved. Once the Monday 06:17 UTC schedule is re-enabled, it will:

1. selects the newest OpenFreeMap version containing both `done` and `tiles.pmtiles` markers;
2. prepares and validates all pinned GeoJSON boundaries;
3. creates a draft release;
4. builds 32 deterministic shards, with at most four running concurrently;
5. verifies every PMTiles file and rejects files at or above 1.9 GiB;
6. publishes only when all 297 packs and checksums are present;
7. retains the newest two published map releases.

Keeping two releases means a weekly snapshot remains available during its build week and the following week. Failed runs delete their incomplete draft and never prune a valid release. Re-running a week whose release is already published is a no-op.

`NAS runner smoke test` can be started manually with a catalog region ID. It verifies the isolated container, records direct OpenFreeMap behavior and attempts an exact regional extraction through the diagnostic split-range proxy, without creating a release.

### Current source blocker

The same Yerevan extraction completed locally in 18 seconds, producing a verified 8.3 MB archive from 138 tiles. On 2026-09-10, [GitHub Actions run 34455972382](https://github.com/g992/anav-map-packs/actions/runs/34455972382) remained inside the same extraction step for 52 minutes and ended when the hosted runner lost communication with GitHub. OpenFreeMap documents high latency for range requests against planet-scale PMTiles on Cloudflare.

The containerized NAS runner is healthy, but its route to the OpenFreeMap Cloudflare bucket stalls after roughly 20 KiB for PMTiles, MBTiles and Btrfs objects. A diagnostic proxy that splits reads into small ranges [successfully built and verified Yerevan](https://github.com/g992/anav-map-packs/actions/runs/34480674217) in 14.6 seconds. A representative Moscow Oblast build reached 51 of 202 MB before some of its tens of thousands of 4 KiB requests exhausted TLS retries in [run 34482314250](https://github.com/g992/anav-map-packs/actions/runs/34482314250). The scheduled trigger remains disabled until the NAS uses a reliable VPN or trusted proxy route and passes both direct-range and representative-region tests.

For comparison, [Protomaps source probe 34469152600](https://github.com/g992/anav-map-packs/actions/runs/34469152600) extracted and verified the same 138 tiles in 6.16 seconds using 35 requests. That source is operationally viable, but it uses the Protomaps basemap layer schema instead of OpenFreeMap's OpenMapTiles schema, so switching it is a product compatibility decision rather than a URL-only fix.

## Local validation

The Python control plane has no third-party dependencies:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/prepare_catalog.py
python3 scripts/discover_openfreemap.py
```

To make one real pack, install `pmtiles` 1.31.2 and run:

```bash
python3 scripts/build_shard.py \
  --source https://btrfs.openfreemap.com/areas/planet/VERSION/tiles.pmtiles \
  --region-id am-er \
  --output-dir dist
```

## Data and attribution

The automation code is MIT licensed. Map tiles and boundary data keep their source licenses. Applications using the packs must display:

> © OpenMapTiles; Data © OpenStreetMap contributors

See [ATTRIBUTION.md](ATTRIBUTION.md) for source links and boundary licensing details.
