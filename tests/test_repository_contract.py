import ast
import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_python_sources_parse(self):
        for path in sorted(ROOT.rglob("*.py")):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_feature_contract(self):
        with (ROOT / "metadata" / "FINAL_BLOCK_BALANCED_FEATURES.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        features = [row["feature"] for row in rows]
        self.assertEqual(len(features), 115)
        self.assertEqual(len(features), len(set(features)))
        contract = json.loads((ROOT / "metadata" / "RF_REDUCED_MODEL_CONTRACT.json").read_text())
        self.assertEqual(contract["feature_count"], len(features))
        self.assertEqual(sum(contract["feature_blocks"].values()), len(features))

    def test_portal_assets(self):
        catalog = json.loads((ROOT / "web" / "layers.json").read_text(encoding="utf-8"))
        ids = {x["id"] for x in catalog}
        self.assertTrue(
            {"frost_probability", "expected_frost_days", "seasonal_tmin", "seasonal_tmin_p25", "hand", "anadem"}.issubset(ids)
        )
        groups = {name: sum(x.get("group") == name for x in catalog) for name in ("complete", "periods", "enso", "terrain")}
        self.assertEqual(groups, {"complete": 4, "periods": 0, "enso": 6, "terrain": 2})
        self.assertNotIn("frost_probability_v2", ids)
        self.assertNotIn("seasonal_tmin_p25_v2", ids)
        for layer in catalog:
            self.assertTrue((ROOT / "web" / layer["url"]).is_file())
            self.assertEqual(layer.get("previewCrs"), "EPSG:3857")
            self.assertEqual(
                layer.get("waterMask"),
                "OpenStreetMap relation 2709093 (Lagoa dos Patos)",
            )
            self.assertGreater(layer.get("waterMaskedCells", 0), 0)
        generated = (ROOT / "web" / "layers.generated.js").read_text(encoding="utf-8")
        self.assertIn("window.FROST_LAYERS", generated)
        self.assertNotIn("window.FROST_LAYERS = [];", generated)
        analysis = json.loads((ROOT / "web" / "analysis-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(analysis), {x["id"] for x in catalog})
        for layer_id, item in analysis.items():
            self.assertGreaterEqual(item["width"], 1024)
            grid = ROOT / "web" / item["url"]
            self.assertTrue(grid.is_file(), layer_id)
            self.assertGreater(grid.stat().st_size, 1000)
            self.assertIn('"projection":"EPSG:3857"', grid.read_text(encoding="utf-8")[:1000])
        manifest_js = (ROOT / "web" / "analysis-manifest.generated.js").read_text(encoding="utf-8")
        self.assertIn("window.FROST_ANALYSIS_MANIFEST", manifest_js)


if __name__ == "__main__":
    unittest.main()
