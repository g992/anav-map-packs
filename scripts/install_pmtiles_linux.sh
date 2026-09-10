#!/usr/bin/env bash
set -euo pipefail

version="1.31.2"
archive="${RUNNER_TEMP:-/tmp}/go-pmtiles_${version}_Linux_x86_64.tar.gz"
destination="${1:-${RUNNER_TEMP:-/tmp}/pmtiles-bin}"
expected="3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f"
url="https://github.com/protomaps/go-pmtiles/releases/download/v${version}/go-pmtiles_${version}_Linux_x86_64.tar.gz"

mkdir -p "$destination"
curl --fail --location --retry 4 --output "$archive" "$url"
printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status
tar -xzf "$archive" -C "$destination"
"$destination/pmtiles" version
