from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.windows import Window


MODULE = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get(
    "FROST_OUTPUT",
    MODULE / "outputs/full_native_five_state_rf_balanced_all_endpoints_period_enso",
))
MARKER_RE = re.compile(r"tile_r(\d+)_c(\d+)\.json$")


def marker_window(marker: Path, width: int, height: int, tile_size: int) -> Window:
    match = MARKER_RE.match(marker.name)
    if match is None:
        raise ValueError(f"Invalid tile marker name: {marker.name}")
    row, col = map(int, match.groups())
    return Window(col, row, min(tile_size, width - col), min(tile_size, height - row))


def main(args: argparse.Namespace) -> int:
    shard_root = OUT / f"shards_{args.tile_size}"
    shards = [shard_root / f"shard_{i:02d}_of_{args.shard_count:02d}" for i in range(args.shard_count)]
    missing_ok = [
        str(path / f"SHARD_{i:02d}_OF_{args.shard_count:02d}_OK")
        for i, path in enumerate(shards)
        if not (path / f"SHARD_{i:02d}_OF_{args.shard_count:02d}_OK").exists()
    ]
    if missing_ok:
        raise RuntimeError(f"Shard completion markers are missing: {missing_ok[:5]}")

    sources: list[tuple[Path, Path]] = []
    global_checkpoints = OUT / "checkpoints"
    global_rasters = OUT / "rasters"
    if global_checkpoints.exists() and any(global_checkpoints.glob("tile_*.json")):
        sources.append((global_checkpoints, global_rasters))
    sources.extend((path / "checkpoints", path / "rasters") for path in shards)

    marker_names: set[str] = set()
    expected_total = None
    for checkpoint_dir, _ in sources:
        for marker in checkpoint_dir.glob("tile_*.json"):
            marker_names.add(marker.name)
            if expected_total is None:
                expected_total = int(json.loads(marker.read_text(encoding="utf-8"))["total"])
    if expected_total is None or len(marker_names) != expected_total:
        raise RuntimeError(
            f"Incomplete tile coverage: unique_markers={len(marker_names)} expected={expected_total}"
        )

    first_raster_dir = shards[0] / "rasters"
    raster_names = sorted(path.name for path in first_raster_dir.glob("*.tif"))
    expected_rasters = int(os.environ.get("FROST_EXPECTED_RASTERS", "27"))
    if len(raster_names) != expected_rasters:
        raise RuntimeError(
            f"Expected {expected_rasters} shard rasters, found {len(raster_names)}"
        )
    final_dir = OUT / "rasters_final"
    final_dir.mkdir(parents=True, exist_ok=True)

    for raster_index, raster_name in enumerate(raster_names, start=1):
        reference = first_raster_dir / raster_name
        with rasterio.open(reference) as ref:
            profile = ref.profile.copy()
            # BIGTIFF is a creation option and is not preserved when reading
            # ``Dataset.profile`` from a shard. The five-state 30 m rasters can
            # exceed the classic TIFF 4 GiB limit during the merge.
            profile.update(BIGTIFF="YES")
            tags = ref.tags()
            width, height = ref.width, ref.height
        destination = final_dir / raster_name
        # A failed classic-TIFF merge can leave a truncated output behind.
        # Recreate only that derived destination; shard rasters remain intact.
        if destination.exists():
            destination.unlink()
        with rasterio.open(destination, "w", **profile) as dst:
            dst.update_tags(**tags, merged_shards=args.shard_count, merged_at=datetime.now(timezone.utc).isoformat())
            written: set[str] = set()
            for checkpoint_dir, raster_dir in sources:
                source_path = raster_dir / raster_name
                if not source_path.exists():
                    raise FileNotFoundError(source_path)
                with rasterio.open(source_path) as src:
                    for marker in sorted(checkpoint_dir.glob("tile_*.json")):
                        if marker.name in written:
                            continue
                        window = marker_window(marker, width, height, args.tile_size)
                        dst.write(src.read(1, window=window), 1, window=window)
                        written.add(marker.name)
            if len(written) != expected_total:
                raise RuntimeError(
                    f"Raster merge incomplete for {raster_name}: {len(written)}/{expected_total} tiles"
                )
        print(
            f"MERGED_RASTER_OK={raster_index}/{expected_rasters} {destination}",
            flush=True,
        )

    final_marker = os.environ.get("FROST_MERGE_MARKER", "FULL_NATIVE_BALANCED_RF_MERGE_OK")
    status = {
        "status": final_marker,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "shards": args.shard_count,
        "tile_size": args.tile_size,
        "tiles": expected_total,
        "rasters": len(raster_names),
        "output": str(final_dir),
    }
    (OUT / "MERGE_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / final_marker).write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--tile-size", type=int, default=512)
    raise SystemExit(main(parser.parse_args()))
