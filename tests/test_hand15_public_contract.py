import csv
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv"
RAW_MATRIX = ROOT / "data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026_RAW.csv"
FEATURES = ROOT / "metadata/FINAL_BLOCK_BALANCED_FEATURES.csv"
AUDIT = ROOT / "data/model_matrix/RF_MODEL_INPUT_HAND15_V2_PROVENANCE.json"


def portable_sha256(path):
    """Hash repository text consistently on Windows and Unix checkouts."""
    payload = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


class Hand15PublicContractTests(unittest.TestCase):
    def test_matrix_matches_frozen_feature_contract(self):
        with FEATURES.open(newline="", encoding="utf-8") as handle:
            features = [row["feature"] for row in csv.DictReader(handle)]
        with MATRIX.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        self.assertEqual(len(features), 115)
        self.assertEqual(reader.fieldnames[-115:], features)
        self.assertEqual(len(rows), 2693)
        self.assertEqual({row["state"] for row in rows}, {"MS", "PR", "RS", "SC", "SP"})
        keys = {(row["state"], row["station_id"], row["year"]) for row in rows}
        self.assertEqual(len(keys), len(rows))
        self.assertEqual(min(int(float(row["year"])) for row in rows), 2001)
        self.assertEqual(max(int(float(row["year"])) for row in rows), 2026)

    def test_matrix_checksum_and_hand_contract(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        digest = portable_sha256(MATRIX)
        self.assertEqual(digest, audit["canonical_csv_sha256"])
        self.assertEqual(audit["hand_flowpath_radius_m"], 15000)
        self.assertEqual(audit["prediction_period"], [2000, 2026])
        self.assertEqual(audit["rows"], 2693)
        self.assertEqual(audit["stations"], 219)
        self.assertEqual(audit["predictor_count"], 115)
        self.assertEqual(audit["imputed_missing_predictor_cells"], 0)

    def test_raw_matrix_preserves_foldwise_imputation_inputs(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        digest = portable_sha256(RAW_MATRIX)
        self.assertEqual(digest, audit["raw_csv_sha256"])
        self.assertGreater(audit["raw_missing_predictor_cells"], 0)


if __name__ == "__main__":
    unittest.main()
