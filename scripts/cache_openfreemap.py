#!/usr/bin/env python3
"""Download and verify one complete OpenFreeMap PMTiles archive for local cuts."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path


CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})\s+\*?(.+)$")
MIN_FREE_AFTER_DOWNLOAD = 10 * 1024**3


def checksum_for(manifest: str, filename: str) -> str:
    for line in manifest.splitlines():
        match = CHECKSUM_RE.match(line.strip())
        if match and match.group(2) == filename:
            return match.group(1)
    raise ValueError(f"checksum for {filename} is missing")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "anav-map-packs/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def remote_size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "anav-map-packs/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        value = response.headers.get("Content-Length")
    if not value:
        raise ValueError("source response has no Content-Length")
    return int(value)


def append_github_output(path: Path, key: str, value: str) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--cache-dir", default="/data/openfreemap")
    parser.add_argument("--github-output")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    final_path = cache_dir / f"tiles-{args.version}.pmtiles"
    partial_path = cache_dir / f"tiles-{args.version}.pmtiles.part"
    for stale_partial in cache_dir.glob("tiles-*.pmtiles.part"):
        if stale_partial != partial_path:
            stale_partial.unlink()
    checksum_url = args.source.rsplit("/", 1)[0] + "/SHA256SUMS"
    expected = checksum_for(fetch_text(checksum_url), "tiles.pmtiles")

    if final_path.exists() and file_sha256(final_path) == expected:
        print(f"using verified cached archive: {final_path}", flush=True)
    else:
        final_path.unlink(missing_ok=True)
        size = remote_size(args.source)
        remaining = max(0, size - (partial_path.stat().st_size if partial_path.exists() else 0))
        free = shutil.disk_usage(cache_dir).free
        if free < remaining + MIN_FREE_AFTER_DOWNLOAD:
            raise RuntimeError(
                f"not enough free space: need {remaining + MIN_FREE_AFTER_DOWNLOAD}, have {free}"
            )
        command = [
            "curl",
            "--fail",
            "--location",
            "--continue-at",
            "-",
            "--retry",
            "10",
            "--retry-all-errors",
            "--retry-delay",
            "15",
            "--speed-limit",
            "1024",
            "--speed-time",
            "300",
            "--output",
            str(partial_path),
            args.source,
        ]
        print("+", " ".join(command), flush=True)
        subprocess.run(command, check=True)
        actual = file_sha256(partial_path)
        if actual != expected:
            raise ValueError(f"source checksum mismatch: expected {expected}, got {actual}")
        os.replace(partial_path, final_path)
        print(f"verified source archive: {final_path}", flush=True)

    for old_path in cache_dir.glob("tiles-*.pmtiles"):
        if old_path != final_path:
            old_path.unlink()

    if args.github_output:
        append_github_output(Path(args.github_output), "source_path", str(final_path))
    else:
        print(f"source_path={final_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
