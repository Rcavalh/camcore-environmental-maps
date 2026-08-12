from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

import pandas as pd


MODULE = Path(__file__).resolve().parents[1]
CONFIG = MODULE / "config" / "source_roots.json"
DATABASE = MODULE / "database"
CHECKPOINT = MODULE / "checkpoints"
SQLITE = DATABASE / "five_state_environment.sqlite"
OFFSETS = CHECKPOINT / "status_log_offsets.json"
STABLE_SECONDS = 120
VERIFY_EVERY_ASSET = os.environ.get("FROST_VERIFY_EVERY_ASSET", "0") == "1"


def load_config():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    project = Path(cfg["project_root"])
    return cfg, project


def resolve(project: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project / path


def init_db(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS raw_assets (
        state_group TEXT NOT NULL, state_codes TEXT NOT NULL,
        source_type TEXT NOT NULL, source_log TEXT NOT NULL,
        collection TEXT, item_id TEXT, acquisition_date TEXT, asset TEXT,
        year_month TEXT, status TEXT, recorded_bytes INTEGER,
        actual_bytes INTEGER, path TEXT NOT NULL, file_mtime TEXT,
        stable INTEGER NOT NULL, catalogued_at TEXT NOT NULL,
        PRIMARY KEY (state_group, source_type, path))"""
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_source_date "
        "ON raw_assets(state_group, source_type, acquisition_date)"
    )


def read_new_rows(log_path: Path, offsets: dict) -> tuple[list[dict], int]:
    key = str(log_path.resolve())
    old = int(offsets.get(key, 0))
    size = log_path.stat().st_size
    if old > size:
        old = 0
    with log_path.open("rb") as handle:
        header = handle.readline()
        header_end = handle.tell()
        if old == 0:
            start = header_end
        else:
            start = max(old, header_end)
        handle.seek(start)
        raw = handle.read()
    if not raw:
        return [], start
    cut = raw.rfind(b"\n")
    if cut < 0:
        return [], start
    complete = raw[: cut + 1]
    text = header.decode("utf-8-sig", errors="replace") + complete.decode(
        "utf-8", errors="replace"
    )
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows, start + len(complete)


def to_record(group, state_codes, source_type, log_path, row):
    if str(row.get("status", "")).upper() != "COMPLETE":
        return None
    raw_path = str(row.get("path", "")).strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    recorded = int(float(row.get("bytes") or 0))
    if VERIFY_EVERY_ASSET:
        try:
            stat = path.stat()
        except OSError:
            return None
        actual_bytes = int(stat.st_size)
        file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        stable = int(
            stat.st_size > 0
            and (recorded <= 0 or stat.st_size == recorded)
            and time.time() - stat.st_mtime >= STABLE_SECONDS
        )
    else:
        # The downloaders append COMPLETE only after closing the destination
        # file and record its final byte size. Avoid millions of remote stat()
        # calls here; every consumer still checks that its selected files open.
        actual_bytes = recorded
        file_mtime = ""
        stable = int(recorded > 0)
    acquisition = row.get("datetime") or ""
    if acquisition:
        acquisition = acquisition[:10]
    elif row.get("year_month"):
        acquisition = str(row["year_month"]).replace("_", "-") + "-01"
    return (
        group, ",".join(state_codes), source_type, str(log_path),
        row.get("collection", ""), row.get("item_id", ""), acquisition,
        row.get("asset", ""), row.get("year_month", ""), "COMPLETE",
        recorded, actual_bytes, str(path), file_mtime,
        stable, datetime.now(timezone.utc).isoformat(),
    )


def upsert(connection, records):
    if not records:
        return
    connection.executemany(
        """INSERT INTO raw_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(state_group, source_type, path) DO UPDATE SET
        status=excluded.status, recorded_bytes=excluded.recorded_bytes,
        actual_bytes=excluded.actual_bytes, file_mtime=excluded.file_mtime,
        stable=excluded.stable, catalogued_at=excluded.catalogued_at""",
        records,
    )


def main():
    DATABASE.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.mkdir(parents=True, exist_ok=True)
    cfg, project = load_config()
    offsets = json.loads(OFFSETS.read_text(encoding="utf-8")) if OFFSETS.exists() else {}
    audit = []
    with sqlite3.connect(SQLITE, timeout=120) as con:
        init_db(con)
        for group, spec in cfg["states"].items():
            roots = {
                "ERA5_LAND": resolve(project, spec["era5"]),
                "MODIS": resolve(project, spec["modis"]),
            }
            for source_type, root in roots.items():
                pattern = "download_status.csv" if source_type == "ERA5_LAND" else "download_status*.csv"
                for log_path in sorted(root.glob(pattern)):
                    rows, new_offset = read_new_rows(log_path, offsets)
                    # Download logs are append-only and may record many retries for
                    # the same output.  Stat each completed path only once, using
                    # its latest COMPLETE row; this is crucial on network storage.
                    complete_by_path = {}
                    for row in rows:
                        if str(row.get("status", "")).upper() == "COMPLETE" and row.get("path"):
                            complete_by_path[str(row["path"])] = row
                    records = [
                        record for row in complete_by_path.values()
                        if (record := to_record(group, spec["state_codes"], source_type, log_path, row)) is not None
                    ]
                    upsert(con, records)
                    offsets[str(log_path.resolve())] = new_offset
                    audit.append({
                        "state_group": group, "source_type": source_type,
                        "source_log": str(log_path), "new_rows_read": len(rows),
                        "distinct_complete_paths": len(complete_by_path),
                        "new_complete_files_catalogued": len(records),
                        "offset_bytes": new_offset,
                    })
                    con.commit()
        assets = pd.read_sql_query("SELECT * FROM raw_assets", con)
    OFFSETS.write_text(json.dumps(offsets, indent=2), encoding="utf-8")
    assets.to_parquet(DATABASE / "AVAILABLE_ENVIRONMENTAL_ASSET_MANIFEST.parquet", index=False)
    assets.groupby(["state_group", "source_type", "collection", "asset", "stable"], dropna=False).agg(
        n_files=("path", "size"), total_bytes=("actual_bytes", "sum"),
        first_date=("acquisition_date", "min"), last_date=("acquisition_date", "max"),
    ).reset_index().to_csv(DATABASE / "ENVIRONMENTAL_ASSET_SUMMARY.csv", index=False)
    pd.DataFrame(audit).to_csv(DATABASE / "INCREMENTAL_CATALOG_UPDATE_AUDIT.csv", index=False)
    status = {
        "status": "FIVE_STATE_ASSET_CATALOG_OK",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "catalogued_assets": int(len(assets)),
        "stable_assets": int(assets.stable.sum()) if len(assets) else 0,
        "states": cfg["states"],
    }
    (DATABASE / "FIVE_STATE_ASSET_CATALOG_STATUS.json").write_text(
        json.dumps(status, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
