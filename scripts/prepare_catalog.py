#!/usr/bin/env python3
"""Download a pinned boundary snapshot and split it into one GeoJSON per pack."""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path


USER_AGENT = "anav-map-packs/1"
URL_TEMPLATE = (
    "https://github.com/wmgeolab/geoBoundaries/raw/{revision}/"
    "releaseData/gbOpen/{iso3}/{level}/"
    "geoBoundaries-{iso3}-{level}_simplified.geojson"
)


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-") or "region"


def download_json(url: str, attempts: int = 4) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except Exception as error:  # network failures are retried with bounded backoff
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def candidate_id(country_code: str, feature: dict) -> str:
    properties = feature.get("properties", {})
    shape_iso = str(properties.get("shapeISO") or "").lower()
    if re.fullmatch(r"[a-z]{2}-[a-z0-9]+", shape_iso):
        return shape_iso
    return f"{country_code}-{slugify(str(properties.get('shapeName') or 'region'))}"


def assign_ids(country_code: str, features: list[dict]) -> list[str]:
    candidates = [candidate_id(country_code, feature) for feature in features]
    counts = Counter(candidates)
    ids: list[str] = []
    for candidate, feature in zip(candidates, features):
        if counts[candidate] == 1:
            ids.append(candidate)
            continue
        shape_id = slugify(str(feature.get("properties", {}).get("shapeID") or "unknown"))
        ids.append(f"{candidate}-{shape_id[-8:]}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"region IDs are not unique for {country_code}")
    return ids


def geometry_bbox(geometry: dict) -> list[float]:
    """Return a GeoJSON bbox as [west, south, east, north].

    The shortest longitude interval is used, so a region crossing the
    antimeridian is represented with west > east instead of a near-global box.
    """

    positions: list[tuple[float, float]] = []

    def collect(value: object) -> None:
        if not isinstance(value, list):
            return
        if (
            len(value) >= 2
            and isinstance(value[0], (int, float))
            and not isinstance(value[0], bool)
            and isinstance(value[1], (int, float))
            and not isinstance(value[1], bool)
        ):
            longitude = float(value[0])
            latitude = float(value[1])
            if not math.isfinite(longitude) or not math.isfinite(latitude):
                raise ValueError("geometry contains a non-finite position")
            if not -90.0 <= latitude <= 90.0:
                raise ValueError("geometry contains an invalid latitude")
            if -180.0 <= longitude <= 180.0:
                normalized = longitude
            else:
                normalized = (longitude + 180.0) % 360.0 - 180.0
            positions.append((normalized, latitude))
            return
        for item in value:
            collect(item)

    if geometry.get("type") == "GeometryCollection":
        for child in geometry.get("geometries", []):
            child_bbox = geometry_bbox(child)
            collect(
                [
                    [child_bbox[0], child_bbox[1]],
                    [child_bbox[2], child_bbox[3]],
                ]
            )
    else:
        collect(geometry.get("coordinates"))

    if not positions:
        raise ValueError("geometry contains no positions")

    longitudes = sorted({position[0] for position in positions})
    if len(longitudes) == 1:
        west = east = longitudes[0]
    else:
        gaps = [
            (longitudes[index + 1] - longitudes[index], index)
            for index in range(len(longitudes) - 1)
        ]
        gaps.append((longitudes[0] + 360.0 - longitudes[-1], len(longitudes) - 1))
        _, gap_index = max(gaps)
        west = longitudes[(gap_index + 1) % len(longitudes)]
        east = longitudes[gap_index]

    latitudes = [position[1] for position in positions]
    return [west, min(latitudes), east, max(latitudes)]


def load_sources(config: dict) -> tuple[dict[tuple[str, str], list[dict]], list[dict]]:
    revision = config["boundary_revision"]
    source_features: dict[tuple[str, str], list[dict]] = {}
    source_metadata: list[dict] = []
    for source in config["sources"]:
        key = (source["iso3"], source["level"])
        url = URL_TEMPLATE.format(revision=revision, iso3=key[0], level=key[1])
        collection = download_json(url)
        if collection.get("type") != "FeatureCollection":
            raise ValueError(f"{key}: expected a GeoJSON FeatureCollection")
        features = collection.get("features", [])
        expected = int(source["expected_count"])
        if len(features) != expected:
            raise ValueError(f"{key}: expected {expected} features, received {len(features)}")
        source_features[key] = features
        source_metadata.append({**source, "url": url})
    return source_features, source_metadata


def build_catalog(config: dict, boundary_dir: Path) -> dict:
    source_features, source_metadata = load_sources(config)
    boundary_dir.mkdir(parents=True, exist_ok=True)
    regions: list[dict] = []

    for source in config["sources"]:
        key = (source["iso3"], source["level"])
        features = source_features[key]
        for region_id, feature in zip(assign_ids(source["country_code"], features), features):
            name = str(feature.get("properties", {}).get("shapeName") or region_id)
            regions.append(
                write_region(
                    boundary_dir,
                    region_id,
                    source["country_code"],
                    name,
                    feature,
                    source["iso3"],
                    source["level"],
                    derived=False,
                )
            )

    for additional in config.get("additional_regions", []):
        key = (additional["source_iso3"], additional["source_level"])
        matches = [
            feature
            for feature in source_features[key]
            if feature.get("properties", {}).get("shapeName") == additional["source_name"]
        ]
        if len(matches) != 1:
            raise ValueError(f"{additional['id']}: expected one source feature, received {len(matches)}")
        regions.append(
            write_region(
                boundary_dir,
                additional["id"],
                additional["country_code"],
                additional["name"],
                matches[0],
                additional["source_iso3"],
                additional["source_level"],
                derived=True,
            )
        )

    regions.sort(key=lambda item: item["id"])
    ids = [item["id"] for item in regions]
    if len(ids) != len(set(ids)):
        raise ValueError("catalog contains duplicate region IDs")
    expected_total = int(config["expected_total_regions"])
    if len(regions) != expected_total:
        raise ValueError(f"expected {expected_total} total regions, received {len(regions)}")

    country_counts = Counter(item["country_code"] for item in regions)
    return {
        "schema_version": 1,
        "boundary_revision": config["boundary_revision"],
        "region_count": len(regions),
        "country_counts": dict(sorted(country_counts.items())),
        "boundary_sources": source_metadata,
        "regions": regions,
    }


def write_region(
    boundary_dir: Path,
    region_id: str,
    country_code: str,
    name: str,
    feature: dict,
    source_iso3: str,
    source_level: str,
    derived: bool,
) -> dict:
    output_name = f"{region_id}.geojson"
    output_path = boundary_dir / output_name
    properties = dict(feature.get("properties", {}))
    properties.update(
        {
            "packId": region_id,
            "packCountry": country_code,
            "packName": name,
            "packDerived": derived,
        }
    )
    output_feature = {"type": "Feature", "properties": properties, "geometry": feature["geometry"]}
    output_path.write_text(
        json.dumps(output_feature, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "id": region_id,
        "country_code": country_code,
        "name": name,
        "bbox": geometry_bbox(feature["geometry"]),
        "boundary": output_name,
        "source_iso3": source_iso3,
        "source_level": source_level,
        "derived": derived,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/boundary-sources.json")
    parser.add_argument("--boundary-dir", default="build/boundaries")
    parser.add_argument("--catalog", default="build/catalog.json")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    catalog = build_catalog(config, Path(args.boundary_dir))
    catalog_path = Path(args.catalog)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"prepared {catalog['region_count']} regional boundaries")
    for country, count in catalog["country_counts"].items():
        print(f"  {country}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
