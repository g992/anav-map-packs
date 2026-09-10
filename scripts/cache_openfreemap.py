#!/usr/bin/env python3
"""Download and verify one complete OpenFreeMap PMTiles archive for local cuts."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.request
from pathlib import Path


CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})\s+\*?(.+)$")
MIN_FREE_AFTER_DOWNLOAD = 10 * 1024**3
DEFAULT_CHUNK_SIZE = 64 * 1024**2
DEFAULT_WORKERS = 12


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


def split_download_ranges(total_size: int, chunk_size: int) -> list[tuple[int, int]]:
    if total_size < 1 or chunk_size < 1:
        raise ValueError("total size and chunk size must be positive")
    return [
        (start, min(start + chunk_size, total_size) - 1)
        for start in range(0, total_size, chunk_size)
    ]


def validate_content_range(value: str | None, start: int, end: int, total_size: int) -> None:
    expected = f"bytes {start}-{end}/{total_size}"
    if value != expected:
        raise ValueError(f"unexpected Content-Range: expected {expected!r}, got {value!r}")


def download_range(
    url: str,
    partial_path: Path,
    marker_path: Path,
    start: int,
    end: int,
    total_size: int,
    attempts: int = 10,
) -> int:
    if marker_path.exists():
        return end - start + 1
    expected_bytes = end - start + 1
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "anav-map-packs/1",
                    "Range": f"bytes={start}-{end}",
                },
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                if response.status != 206:
                    raise ValueError(f"range request returned HTTP {response.status}")
                validate_content_range(response.headers.get("Content-Range"), start, end, total_size)
                written = 0
                descriptor = os.open(partial_path, os.O_WRONLY)
                try:
                    while block := response.read(8 * 1024 * 1024):
                        os.pwrite(descriptor, block, start + written)
                        written += len(block)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            if written != expected_bytes:
                raise ValueError(f"range {start}-{end} returned {written} bytes, expected {expected_bytes}")
            marker_path.write_text(f"{start}-{end}\n", encoding="ascii")
            return written
        except Exception as error:
            if attempt == attempts:
                raise RuntimeError(f"range {start}-{end} failed after {attempts} attempts") from error
            print(f"range {start}-{end} attempt {attempt} failed: {error}; retrying", flush=True)
            time.sleep(15)
    raise AssertionError("unreachable")


def download_parallel(
    url: str,
    partial_path: Path,
    total_size: int,
    workers: int,
    chunk_size: int,
) -> None:
    if workers < 1:
        raise ValueError("download workers must be positive")
    ranges = split_download_ranges(total_size, chunk_size)
    state_dir = partial_path.with_suffix(partial_path.suffix + ".ranges")
    metadata_path = state_dir / "metadata.json"
    metadata = {"url": url, "total_size": total_size, "chunk_size": chunk_size}
    reset = True
    if metadata_path.exists() and partial_path.exists() and partial_path.stat().st_size == total_size:
        try:
            reset = json.loads(metadata_path.read_text(encoding="utf-8")) != metadata
        except (OSError, ValueError):
            reset = True
    if reset:
        partial_path.unlink(missing_ok=True)
        shutil.rmtree(state_dir, ignore_errors=True)
        state_dir.mkdir(parents=True)
        with partial_path.open("wb") as output:
            output.truncate(total_size)
        metadata_path.write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")

    completed = sum((state_dir / f"{index:06d}.done").exists() for index in range(len(ranges)))
    completed_lock = threading.Lock()

    def worker(index: int, byte_range: tuple[int, int]) -> int:
        nonlocal completed
        start, end = byte_range
        result = download_range(
            url,
            partial_path,
            state_dir / f"{index:06d}.done",
            start,
            end,
            total_size,
        )
        with completed_lock:
            completed += 1
            print(
                f"downloaded range {completed}/{len(ranges)} "
                f"({completed * 100 / len(ranges):.1f}%)",
                flush=True,
            )
        return result

    print(
        f"downloading {total_size} bytes in {len(ranges)} ranges with {workers} workers; "
        f"resuming at {completed}/{len(ranges)}",
        flush=True,
    )
    pending = [
        (index, byte_range)
        for index, byte_range in enumerate(ranges)
        if not (state_dir / f"{index:06d}.done").exists()
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, index, byte_range) for index, byte_range in pending]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def append_github_output(path: Path, key: str, value: str) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--cache-dir", default="/data/openfreemap")
    parser.add_argument("--download-workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--range-chunk-mib", type=int, default=DEFAULT_CHUNK_SIZE // 1024**2)
    parser.add_argument("--github-output")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    final_path = cache_dir / f"tiles-{args.version}.pmtiles"
    partial_path = cache_dir / f"tiles-{args.version}.pmtiles.part"
    for stale_partial in cache_dir.glob("tiles-*.pmtiles.part"):
        if stale_partial != partial_path:
            stale_partial.unlink()
            shutil.rmtree(stale_partial.with_suffix(stale_partial.suffix + ".ranges"), ignore_errors=True)
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
        download_parallel(
            args.source,
            partial_path,
            size,
            args.download_workers,
            args.range_chunk_mib * 1024**2,
        )
        actual = file_sha256(partial_path)
        if actual != expected:
            partial_path.unlink(missing_ok=True)
            shutil.rmtree(partial_path.with_suffix(partial_path.suffix + ".ranges"), ignore_errors=True)
            raise ValueError(f"source checksum mismatch: expected {expected}, got {actual}")
        os.replace(partial_path, final_path)
        shutil.rmtree(partial_path.with_suffix(partial_path.suffix + ".ranges"), ignore_errors=True)
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
