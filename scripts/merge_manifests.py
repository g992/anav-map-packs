#!/usr/bin/env python3
"""Merge shard manifests and require exact coverage before a release is published."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def merge(catalog: dict, fragments: list[dict], release_tag: str, ofm_version: str) -> dict:
    expected_shards = {fragment["shard_count"] for fragment in fragments}
    if len(expected_shards) != 1:
        raise ValueError("shard manifests disagree on shard_count")
    shard_count = expected_shards.pop()
    seen_shards = {fragment["shard_index"] for fragment in fragments}
    if seen_shards != set(range(shard_count)):
        raise ValueError(f"expected shard indexes 0..{shard_count - 1}, received {sorted(seen_shards)}")
    regions = sorted(
        (region for fragment in fragments for region in fragment["regions"]),
        key=lambda region: region["id"],
    )
    expected_ids = {region["id"] for region in catalog["regions"]}
    actual_ids = [region["id"] for region in regions]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("duplicate region IDs in shard manifests")
    if set(actual_ids) != expected_ids:
        missing = sorted(expected_ids - set(actual_ids))
        extra = sorted(set(actual_ids) - expected_ids)
        raise ValueError(f"release coverage mismatch; missing={missing}, extra={extra}")
    return {
        "schema_version": 1,
        "release_tag": release_tag,
        "openfreemap_version": ofm_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "region_count": len(regions),
        "country_counts": catalog["country_counts"],
        "attribution": "© OpenMapTiles; Data © OpenStreetMap contributors",
        "regions": regions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--fragments", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--ofm-version", required=True)
    parser.add_argument("--output", default="dist/manifest.json")
    parser.add_argument("--checksums", default="dist/SHA256SUMS")
    parser.add_argument("--notes", default="dist/release-notes.md")
    args = parser.parse_args()

    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    fragment_paths = sorted(Path().glob(args.fragments))
    fragments = [json.loads(path.read_text(encoding="utf-8")) for path in fragment_paths]
    if not fragments:
        raise ValueError("no shard manifests found")
    manifest = merge(catalog, fragments, args.release_tag, args.ofm_version)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.checksums).write_text(
        "".join(f"{region['sha256']}  {region['asset']}\n" for region in manifest["regions"]),
        encoding="utf-8",
    )
    Path(args.notes).write_text(
        f"OpenFreeMap `{args.ofm_version}`: {manifest['region_count']} regional PMTiles packs.\n\n"
        "Download `manifest.json` first; it contains names, sizes, SHA-256 checksums and direct URLs.\n\n"
        "Attribution: © OpenMapTiles; Data © OpenStreetMap contributors.\n",
        encoding="utf-8",
    )
    print(f"merged {len(fragments)} shards and {manifest['region_count']} regions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

