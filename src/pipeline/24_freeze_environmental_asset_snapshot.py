from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


MODULE = Path(__file__).resolve().parents[1]
DB = MODULE / "database"
SOURCE = DB / "AVAILABLE_ENVIRONMENTAL_ASSET_MANIFEST.parquet"
SNAPSHOT_DIR = DB / "snapshots/final_environmental_snapshot_20260806"
SNAPSHOT = SNAPSHOT_DIR / "AVAILABLE_ENVIRONMENTAL_ASSET_MANIFEST_FROZEN.parquet"
CONTRACT = SNAPSHOT_DIR / "FINAL_ENVIRONMENTAL_SNAPSHOT_CONTRACT.json"


def main() -> int:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(SOURCE)
    frame = frame.loc[frame.stable.fillna(False).astype(bool)].copy()
    frame = frame.sort_values(["source_type", "state_group", "collection", "asset", "acquisition_date", "path"])
    frame.to_parquet(SNAPSHOT, index=False)
    digest = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    modis = frame.loc[frame.source_type.eq("MODIS")]
    era5 = frame.loc[frame.source_type.eq("ERA5_LAND_DAILY")]
    status = {
        "status": "FINAL_ENVIRONMENTAL_SNAPSHOT_FROZEN",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "policy": "All stable assets present at freeze time; incomplete early product years are allowed and audited.",
        "manifest": str(SNAPSHOT),
        "sha256": digest,
        "rows": int(len(frame)),
        "modis_files": int(len(modis)),
        "modis_collections": sorted(modis.collection.dropna().unique().tolist()),
        "modis_assets": int(modis.asset.nunique()),
        "era5_files": int(len(era5)),
        "state_groups": sorted(frame.state_group.dropna().unique().tolist()),
    }
    CONTRACT.write_text(json.dumps(status, indent=2), encoding="utf-8")
    (SNAPSHOT_DIR / "FINAL_ENVIRONMENTAL_SNAPSHOT_FROZEN").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
