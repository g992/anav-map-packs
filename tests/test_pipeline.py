import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from scripts.build_shard import shard_for
from scripts.cache_openfreemap import (
    checksum_for,
    download_parallel,
    split_download_ranges,
    validate_content_range,
)
from scripts.discover_openfreemap import newest_complete_version
from scripts.merge_manifests import merge
from scripts.prepare_catalog import assign_ids, candidate_id, geometry_bbox, slugify
from scripts.range_proxy import parse_range, split_range
from scripts.release_admin import delete_release, get_release, release_assets


class DiscoverTests(unittest.TestCase):
    def test_newest_complete_pmtiles_build(self):
        index = "\n".join(
            [
                "areas/planet/20260101_pt/done",
                "areas/planet/20260101_pt/tiles.pmtiles",
                "areas/planet/20260108_pt/done",
                "areas/planet/20260115_pt/tiles.pmtiles",
                "areas/planet/20260115_pt/done",
            ]
        )
        self.assertEqual(newest_complete_version(index), "20260115_pt")

    def test_rejects_incomplete_index(self):
        with self.assertRaises(ValueError):
            newest_complete_version("areas/planet/20260101_pt/done\n")

    def test_selects_pmtiles_checksum(self):
        manifest = "a" * 64 + "  tiles.mbtiles\n" + "b" * 64 + "  tiles.pmtiles\n"
        self.assertEqual(checksum_for(manifest, "tiles.pmtiles"), "b" * 64)

    def test_rejects_missing_pmtiles_checksum(self):
        with self.assertRaises(ValueError):
            checksum_for("a" * 64 + "  tiles.mbtiles\n", "tiles.pmtiles")

    def test_splits_parallel_download_without_gaps(self):
        self.assertEqual(split_download_ranges(10, 4), [(0, 3), (4, 7), (8, 9)])

    def test_validates_exact_content_range(self):
        validate_content_range("bytes 4-7/10", 4, 7, 10)
        with self.assertRaises(ValueError):
            validate_content_range("bytes 4-8/10", 4, 7, 10)

    def test_parallel_range_download_writes_exact_file(self):
        content = bytes(range(256)) * 16

        class Response(io.BytesIO):
            status = 206

            def __init__(self, body, content_range):
                super().__init__(body)
                self.headers = {"Content-Range": content_range}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        def urlopen(request, timeout):
            self.assertEqual(timeout, 300)
            start_text, end_text = request.get_header("Range").removeprefix("bytes=").split("-")
            start, end = int(start_text), int(end_text)
            return Response(content[start : end + 1], f"bytes {start}-{end}/{len(content)}")

        with patch("scripts.cache_openfreemap.urllib.request.urlopen", side_effect=urlopen):
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "source.part"
                download_parallel("https://example.test/source", destination, len(content), workers=4, chunk_size=333)
                self.assertEqual(destination.read_bytes(), content)


class CatalogTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Vayots Dzor"), "vayots-dzor")

    def test_prefers_iso_code(self):
        feature = {"properties": {"shapeISO": "AM-ER", "shapeName": "Yerevan"}}
        self.assertEqual(candidate_id("am", feature), "am-er")

    def test_duplicate_names_receive_stable_suffixes(self):
        features = [
            {"properties": {"shapeISO": "AZE", "shapeName": "Lankaran", "shapeID": "abc11111"}},
            {"properties": {"shapeISO": "AZE", "shapeName": "Lankaran", "shapeID": "abc22222"}},
        ]
        self.assertEqual(assign_ids("az", features), ["az-lankaran-abc11111", "az-lankaran-abc22222"])

    def test_sharding_is_stable(self):
        self.assertEqual(shard_for("am-er", 32), shard_for("am-er", 32))
        self.assertIn(shard_for("am-er", 32), range(32))

    def test_computes_bbox_for_nested_geometry(self):
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[2.5, 8], [10, -3], [2.5, 8]]],
                [[[-2.5, 4], [4, 6], [-2.5, 4]]],
            ],
        }
        self.assertEqual(geometry_bbox(geometry), [-2.5, -3.0, 10.0, 8.0])

    def test_rejects_geometry_without_positions(self):
        with self.assertRaises(ValueError):
            geometry_bbox({"type": "Polygon", "coordinates": []})

    def test_bbox_uses_short_interval_across_antimeridian(self):
        geometry = {
            "type": "Polygon",
            "coordinates": [[[178, 2], [179, 4], [-179, 3], [178, 2]]],
        }
        self.assertEqual(geometry_bbox(geometry), [178.0, 2.0, -179.0, 4.0])


class ManifestTests(unittest.TestCase):
    def test_requires_complete_exact_coverage(self):
        catalog = {
            "country_counts": {"am": 2},
            "regions": [
                {"id": "am-a", "bbox": [1.0, 2.0, 3.0, 4.0]},
                {"id": "am-b", "bbox": [5.0, 6.0, 7.0, 8.0]},
            ],
        }
        fragments = [
            {"shard_count": 2, "shard_index": 0, "regions": [{"id": "am-b"}]},
            {"shard_count": 2, "shard_index": 1, "regions": [{"id": "am-a"}]},
        ]
        manifest = merge(catalog, fragments, "maps-test", "test")
        self.assertEqual([item["id"] for item in manifest["regions"]], ["am-a", "am-b"])
        self.assertEqual(manifest["regions"][0]["bbox"], [1.0, 2.0, 3.0, 4.0])

    def test_rejects_missing_region(self):
        catalog = {
            "country_counts": {"am": 1},
            "regions": [{"id": "am-a", "bbox": [1.0, 2.0, 3.0, 4.0]}],
        }
        fragments = [{"shard_count": 1, "shard_index": 0, "regions": []}]
        with self.assertRaises(ValueError):
            merge(catalog, fragments, "maps-test", "test")

    def test_rejects_missing_catalog_bbox(self):
        catalog = {"country_counts": {"am": 1}, "regions": [{"id": "am-a"}]}
        fragments = [
            {"shard_count": 1, "shard_index": 0, "regions": [{"id": "am-a"}]}
        ]
        with self.assertRaisesRegex(ValueError, "invalid bbox"):
            merge(catalog, fragments, "maps-test", "test")


class ReleaseAdminTests(unittest.TestCase):
    @patch("scripts.release_admin.gh")
    def test_finds_draft_when_tag_endpoint_omits_it(self, gh_mock):
        draft = {"id": 42, "tag_name": "maps-test", "draft": True}
        gh_mock.side_effect = [
            subprocess.CompletedProcess([], 1, "", "not found"),
            subprocess.CompletedProcess([], 0, json.dumps([draft]), ""),
        ]
        self.assertEqual(get_release("owner/repo", "maps-test"), draft)

    @patch("scripts.release_admin.gh")
    def test_deletes_release_before_optional_tag_ref(self, gh_mock):
        delete_release("owner/repo", {"id": 42, "tag_name": "maps-test"})
        self.assertEqual(
            gh_mock.call_args_list,
            [
                call(
                    ["api", "--method", "DELETE", "repos/owner/repo/releases/42"]
                ),
                call(
                    ["api", "--method", "DELETE", "repos/owner/repo/git/refs/tags/maps-test"],
                    check=False,
                ),
            ],
        )

    @patch("scripts.release_admin.gh")
    def test_collects_all_release_asset_pages(self, gh_mock):
        first_page = [{"id": index} for index in range(100)]
        second_page = [{"id": 100}]
        gh_mock.side_effect = [
            subprocess.CompletedProcess([], 0, json.dumps(first_page), ""),
            subprocess.CompletedProcess([], 0, json.dumps(second_page), ""),
        ]
        self.assertEqual(len(release_assets("owner/repo", 42)), 101)
        self.assertIn("page=2", gh_mock.call_args_list[1].args[0][-1])


class RangeProxyTests(unittest.TestCase):
    def test_parses_bounded_and_open_ranges(self):
        self.assertEqual(parse_range("bytes=10-19", 100), (10, 19))
        self.assertEqual(parse_range("bytes=90-", 100), (90, 99))

    def test_rejects_invalid_ranges(self):
        for value in (None, "bytes=-10", "bytes=20-10", "bytes=0-100", "bytes=0-1,4-5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_range(value, 100)

    def test_splits_inclusive_range_without_gaps(self):
        self.assertEqual(split_range(10, 30, 8), [(10, 17), (18, 25), (26, 30)])


if __name__ == "__main__":
    unittest.main()
