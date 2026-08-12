#!/usr/bin/env python3
"""Audit and catalogue the final Dryad package without reading full raster arrays."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import rasterio


PORTAL_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = PORTAL_ROOT / "dryad_dataset"
METADATA_ROOT = DATASET_ROOT / "metadata"

EXPECTED_RASTERS = (
    "data/model_outputs/complete_period/FROST_PROBABILITY_MEAN_2000_2025.tif",
    "data/model_outputs/complete_period/FROST_DAYS_MEAN_2000_2025.tif",
    "data/model_outputs/complete_period/TMIN_MEAN_2000_2025.tif",
    "data/model_outputs/complete_period/TMIN_P25_2000_2025.tif",
    "data/derived_terrain/HAND_2000M.tif",
)
REQUIRED_DOCUMENTATION = (
    "README.txt",
    "documentation/METHODS_AND_PROVENANCE.md",
    "documentation/THIRD_PARTY_SOURCES.md",
    "metadata/DATA_DICTIONARY.csv",
    "metadata/SHA256SUMS_DATA.txt",
)


def category(relative: str) -> str:
    if relative.startswith("data/model_outputs/complete_period/"):
        return "complete_period_model_output"
    if relative.startswith("data/derived_terrain/"):
        return "derived_terrain"
    if relative.startswith("metadata/"):
        return "metadata"
    if relative.startswith("documentation/"):
        return "documentation"
    if relative == "README.txt":
        return "readme"
    return "other"


def raster_record(relative: str) -> dict[str, object]:
    path = DATASET_ROOT / relative
    record: dict[str, object] = {"relative_path": relative, "valid": False}
    if not path.is_file() or path.stat().st_size == 0:
        record["error"] = "missing or empty"
        return record
    try:
        with rasterio.open(path) as src:
            record.update(
                {
                    "valid": bool(
                        src.count == 1
                        and src.width > 0
                        and src.height > 0
                        and src.crs is not None
                    ),
                    "width": src.width,
                    "height": src.height,
                    "bands": src.count,
                    "dtype": src.dtypes[0],
                    "crs": str(src.crs),
                    "nodata": src.nodata,
                    "transform": list(src.transform)[:6],
                    "bounds": list(src.bounds),
                    "bytes": path.stat().st_size,
                }
            )
    except Exception as exc:  # pragma: no cover - defensive audit path
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def write_catalog(records: list[dict[str, object]]) -> None:
    fields = [
        "relative_path", "valid", "width", "height", "bands", "dtype",
        "crs", "nodata", "transform", "bounds", "bytes",
    ]
    with (METADATA_ROOT / "RASTER_CATALOG.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def write_manifest() -> list[dict[str, object]]:
    manifest_path = METADATA_ROOT / "DRYAD_UPLOAD_MANIFEST.csv"
    files = sorted(
        path
        for path in DATASET_ROOT.rglob("*")
        if path.is_file() and path != manifest_path
    )
    rows = []
    for path in files:
        relative = path.relative_to(DATASET_ROOT).as_posix()
        rows.append(
            {
                "relative_path": relative,
                "category": category(relative),
                "bytes": path.stat().st_size,
                "megabytes": round(path.stat().st_size / 1024**2, 3),
                "include_in_dryad_upload": "YES",
                "exclusion_reason": "",
            }
        )
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> int:
    METADATA_ROOT.mkdir(parents=True, exist_ok=True)
    records = [raster_record(relative) for relative in EXPECTED_RASTERS]
    write_catalog(records)

    blockers: list[str] = []
    actual_rasters = {
        path.relative_to(DATASET_ROOT).as_posix()
        for path in DATASET_ROOT.rglob("*.tif")
    }
    if actual_rasters != set(EXPECTED_RASTERS):
        blockers.append("UNEXPECTED_RASTER_SET")
    if not all(bool(record.get("valid")) for record in records):
        blockers.append("INVALID_RASTER_METADATA")

    reference = records[0]
    common_grid = all(
        record.get("width") == reference.get("width")
        and record.get("height") == reference.get("height")
        and record.get("crs") == reference.get("crs")
        and record.get("transform") == reference.get("transform")
        for record in records
    )
    if not common_grid:
        blockers.append("RASTERS_NOT_ON_EXACT_COMMON_GRID")

    missing_docs = [
        relative
        for relative in REQUIRED_DOCUMENTATION
        if not (DATASET_ROOT / relative).is_file()
        or (DATASET_ROOT / relative).stat().st_size == 0
    ]
    if missing_docs:
        blockers.append("REQUIRED_DOCUMENTATION_MISSING")

    all_files = [path for path in DATASET_ROOT.rglob("*") if path.is_file()]
    if any(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"} for path in all_files):
        blockers.append("FIGURE_OR_PRESENTATION_FILE_PRESENT")
    if any(path.name.lower().endswith(".aux.xml") for path in all_files):
        blockers.append("GIS_SIDECAR_PRESENT")

    checksum_path = METADATA_ROOT / "SHA256SUMS_DATA.txt"
    checksum_text = checksum_path.read_text(encoding="utf-8") if checksum_path.is_file() else ""
    if any(Path(relative).name not in checksum_text for relative in EXPECTED_RASTERS):
        blockers.append("INCOMPLETE_DATA_CHECKSUMS")

    audit = {
        "audit_date": date.today().isoformat(),
        "dataset_root": ".",
        "status": "BLOCKED" if blockers else "READY",
        "blockers": blockers,
        "expected_raster_count": len(EXPECTED_RASTERS),
        "valid_raster_count": sum(bool(record.get("valid")) for record in records),
        "exact_common_grid": common_grid,
        "missing_documentation": missing_docs,
        "scope": "complete-period 2000-2025 products and HAND only",
        "rasters": records,
    }
    (METADATA_ROOT / "DRYAD_UPLOAD_AUDIT.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    rows = write_manifest()
    included_bytes = sum(int(row["bytes"]) for row in rows) + (
        METADATA_ROOT / "DRYAD_UPLOAD_MANIFEST.csv"
    ).stat().st_size
    audit.update(
        {
            "upload_file_count_including_manifest": len(rows) + 1,
            "upload_size_bytes": included_bytes,
            "upload_size_gib": round(included_bytes / 1024**3, 3),
            "below_50_gb_decimal": included_bytes < 50_000_000_000,
            "manifest_note": "The manifest inventories every upload file except itself.",
        }
    )
    if included_bytes >= 50_000_000_000:
        audit["blockers"].append("NCSU_FREE_TIER_EXCEEDED")
        audit["status"] = "BLOCKED"
    (METADATA_ROOT / "DRYAD_UPLOAD_AUDIT.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_manifest()

    print(json.dumps({key: value for key, value in audit.items() if key != "rasters"}, indent=2))
    return 0 if audit["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
