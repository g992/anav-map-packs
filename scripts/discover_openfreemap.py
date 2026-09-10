#!/usr/bin/env python3
"""Find the newest completed OpenFreeMap planet build that contains PMTiles."""

from __future__ import annotations

import argparse
import re
import urllib.request
from pathlib import Path


INDEX_URL = "https://btrfs.openfreemap.com/files.txt"
BASE_URL = "https://btrfs.openfreemap.com/areas/planet"
DONE_RE = re.compile(r"^areas/planet/([^/]+)/done$")


def newest_complete_version(index: str) -> str:
    paths = set(index.splitlines())
    versions = sorted(
        match.group(1)
        for line in paths
        if (match := DONE_RE.match(line))
        and f"areas/planet/{match.group(1)}/tiles.pmtiles" in paths
    )
    if not versions:
        raise ValueError("OpenFreeMap index has no completed planet PMTiles build")
    return versions[-1]


def fetch_index() -> str:
    request = urllib.request.Request(INDEX_URL, headers={"User-Agent": "anav-map-packs/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def append_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-file")
    parser.add_argument("--github-output")
    args = parser.parse_args()
    index = Path(args.index_file).read_text(encoding="utf-8") if args.index_file else fetch_index()
    version = newest_complete_version(index)
    values = {
        "ofm_version": version,
        "source_url": f"{BASE_URL}/{version}/tiles.pmtiles",
        "release_tag": f"maps-{version}",
    }
    for key, value in values.items():
        print(f"{key}={value}")
    if args.github_output:
        append_github_output(Path(args.github_output), values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

