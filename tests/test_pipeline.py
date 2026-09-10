import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_shard import shard_for
from scripts.discover_openfreemap import newest_complete_version
from scripts.merge_manifests import merge
from scripts.prepare_catalog import assign_ids, candidate_id, slugify


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


class ManifestTests(unittest.TestCase):
    def test_requires_complete_exact_coverage(self):
        catalog = {
            "country_counts": {"am": 2},
            "regions": [{"id": "am-a"}, {"id": "am-b"}],
        }
        fragments = [
            {"shard_count": 2, "shard_index": 0, "regions": [{"id": "am-b"}]},
            {"shard_count": 2, "shard_index": 1, "regions": [{"id": "am-a"}]},
        ]
        manifest = merge(catalog, fragments, "maps-test", "test")
        self.assertEqual([item["id"] for item in manifest["regions"]], ["am-a", "am-b"])

    def test_rejects_missing_region(self):
        catalog = {"country_counts": {"am": 1}, "regions": [{"id": "am-a"}]}
        fragments = [{"shard_count": 1, "shard_index": 0, "regions": []}]
        with self.assertRaises(ValueError):
            merge(catalog, fragments, "maps-test", "test")


if __name__ == "__main__":
    unittest.main()

