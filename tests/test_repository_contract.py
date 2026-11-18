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
            {"frost_probability", "expected_frost_days", "seasonal_tmin", "seasonal_tmin_p05", "frost_probability_classes", "hand", "hand_15km", "anadem"}.issubset(ids)
        )
        groups = {name: sum(x.get("group") == name for x in catalog) for name in ("complete", "periods", "enso", "terrain", "classes")}
        self.assertEqual(groups, {"complete": 4, "periods": 0, "enso": 3, "terrain": 3, "classes": 1})
        self.assertFalse(any("p25" in layer_id.lower() or "species" in layer_id.lower() for layer_id in ids))
        home_page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-href="species.html"', home_page)
        self.assertIn('<strong>5</strong> <span data-i18n="collections_count">', home_page)
        species_page = (ROOT / "web" / "species.html").read_text(encoding="utf-8")
        self.assertNotIn('http-equiv="refresh"', species_page)
        self.assertIn('id="species-map"', species_page)
        self.assertIn('species.generated.js', species_page)
        self.assertIn('species.js', species_page)
        species_css = (ROOT / "web" / "species.css").read_text(encoding="utf-8")
        self.assertIn('linear-gradient(90deg,#ffffcc,#d9f0a3,#addd8e,#4eb369,#006d2c,#003814)', species_css)
        species_catalog_source = (ROOT / "web" / "species.generated.js").read_text(encoding="utf-8")
        species_catalog = json.loads(species_catalog_source.split("=", 1)[1].strip().rstrip(";"))
        self.assertEqual(len(species_catalog["previewSpecies"]), 52)
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
