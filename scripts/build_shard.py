#!/usr/bin/env python3
"""Extract, verify, checksum and optionally upload one deterministic pack shard."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


MAX_ASSET_BYTES = 1_900 * 1024 * 1024


def shard_for(region_id: str, shard_count: int) -> int:
    digest = hashlib.sha256(region_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked(command: list[str], *, timeout_seconds: int | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, timeout=timeout_seconds)


def selected_regions(catalog: dict, shard_index: int, shard_count: int, region_id: str | None) -> list[dict]:
    regions = catalog["regions"]
    if region_id:
        matches = [region for region in regions if region["id"] == region_id]
        if len(matches) != 1:
            raise ValueError(f"unknown region ID: {region_id}")
        return matches
    return [region for region in regions if shard_for(region["id"], shard_count) == shard_index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="build/catalog.json")
    parser.add_argument("--boundary-dir", default="build/boundaries")
    parser.add_argument("--output-dir", default="dist")
    parser.add_argument("--source", required=True)
    parser.add_argument("--pmtiles", default="pmtiles")
    parser.add_argument("--maxzoom", type=int, default=14)
    parser.add_argument("--download-threads", type=int, default=4)
    parser.add_argument("--extract-timeout-seconds", type=int, default=2700)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--region-id")
    parser.add_argument("--release-tag")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    args = parser.parse_args()

    if args.shard_count < 1 or args.shard_index not in range(args.shard_count):
        raise ValueError("invalid shard index/count")
    if args.extract_timeout_seconds < 1:
        raise ValueError("--extract-timeout-seconds must be positive")
    if args.release_tag and not args.repo:
        raise ValueError("--repo is required when uploading to a release")

    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    regions = selected_regions(catalog, args.shard_index, args.shard_count, args.region_id)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    print(f"shard {args.shard_index}/{args.shard_count}: {len(regions)} region(s)")
    for region in regions:
        boundary = Path(args.boundary_dir) / region["boundary"]
        asset = f"{region['id']}.pmtiles"
        output = output_dir / asset
        if output.exists():
            output.unlink()
        command = [
            args.pmtiles,
            "extract",
            args.source,
            str(output),
            f"--region={boundary}",
            f"--maxzoom={args.maxzoom}",
            f"--download-threads={args.download_threads}",
            "--overfetch=0.05",
        ]
        try:
            checked(command, timeout_seconds=args.extract_timeout_seconds)
            checked([args.pmtiles, "verify", str(output)])
            size = output.stat().st_size
            if size <= 0:
                raise ValueError(f"{asset} is empty")
            if size >= MAX_ASSET_BYTES:
                raise ValueError(f"{asset} is {size} bytes; release safety limit is {MAX_ASSET_BYTES}")
            digest = file_sha256(output)
            entry = {
                **region,
                "asset": asset,
                "bytes": size,
                "sha256": digest,
                "maxzoom": args.maxzoom,
                "source": args.source,
            }
            if args.release_tag:
                checked(["gh", "release", "upload", args.release_tag, str(output), "--repo", args.repo])
                entry["download_url"] = (
                    f"https://github.com/{args.repo}/releases/download/"
                    f"{quote(args.release_tag)}/{quote(asset)}"
                )
                output.unlink()
            entries.append(entry)
        except Exception:
            output.unlink(missing_ok=True)
            raise

    fragment = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "regions": entries,
    }
    fragment_path = output_dir / f"manifest-shard-{args.shard_index:02d}.json"
    fragment_path.write_text(json.dumps(fragment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.release_tag:
        checked(["gh", "release", "upload", args.release_tag, str(fragment_path), "--repo", args.repo])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
