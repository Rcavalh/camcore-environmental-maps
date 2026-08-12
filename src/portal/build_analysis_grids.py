#!/usr/bin/env python
"""Build browser-readable numeric grids for point queries and area summaries."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from build_web_layers import LAYER_SPECS, WEB


NODATA = 65535
MAX_VALUE = 65534


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--width",
        type=int,
        default=2048,
        help="Width of each numeric analysis grid used in the browser.",
    )
    args = parser.parse_args()

    catalog = {
        item["id"]: item
        for item in json.loads((WEB / "layers.json").read_text(encoding="utf-8"))
    }
    output_dir = WEB / "assets" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    for spec in LAYER_SPECS:
        layer = catalog[spec["id"]]
        preview = WEB / "assets" / "layers" / spec["output"]
        with Image.open(preview) as image:
            requested_width = min(args.width, spec.get("analysis_width", args.width))
            scale = min(1.0, requested_width / image.width)
            width = max(1, int(round(image.width * scale)))
            height = max(1, int(round(image.height * scale)))
            rgba = np.asarray(
                image.convert("RGBA").resize((width, height), Image.Resampling.NEAREST)
            )
        valid = rgba[..., 3] > 0
        packed = (
            (rgba[..., 0].astype("uint32") << 16)
            | (rgba[..., 1].astype("uint32") << 8)
            | rgba[..., 2].astype("uint32")
        )
        palette = plt.get_cmap(spec["cmap"])(np.linspace(0, 1, 256), bytes=True)[:, :3]
        palette_packed = (
            (palette[:, 0].astype("uint32") << 16)
            | (palette[:, 1].astype("uint32") << 8)
            | palette[:, 2].astype("uint32")
        )
        lookup = {int(color): index for index, color in enumerate(palette_packed)}
        palette_index = np.zeros((height, width), dtype="uint16")
        for color in np.unique(packed[valid]):
            if int(color) not in lookup:
                raise RuntimeError(f"Unexpected preview color {int(color)} in {preview}")
            palette_index[packed == color] = lookup[int(color)]

        minimum = float(layer["displayMin"])
        maximum = float(layer["displayMax"])
        encoded = np.full((height, width), NODATA, dtype="<u2")
        encoded[valid] = np.rint(palette_index[valid] / 255 * MAX_VALUE).astype("<u2")
        payload = base64.b64encode(encoded.tobytes(order="C")).decode("ascii")

        filename = f"{spec['id']}.generated.js"
        grid = {
            "id": spec["id"],
            "width": width,
            "height": height,
            "bounds": layer["bounds"],
            "projection": layer.get("previewCrs", "EPSG:4326"),
            "minimum": minimum,
            "maximum": maximum,
            "nodata": NODATA,
            "quantizedMaximum": MAX_VALUE,
            "units": layer["units"],
            "data": payload,
        }
        (output_dir / filename).write_text(
            "window.FROST_ANALYSIS_GRIDS = window.FROST_ANALYSIS_GRIDS || {};\n"
            f"window.FROST_ANALYSIS_GRIDS[{json.dumps(spec['id'])}] = "
            f"{json.dumps(grid, separators=(',', ':'))};\n",
            encoding="utf-8",
        )
        manifest[spec["id"]] = {
            "url": f"assets/analysis/{filename}",
            "width": width,
            "height": height,
            "sourceWidth": layer["nativeWidth"],
            "sourceHeight": layer["nativeHeight"],
        }
        print(f"ANALYSIS_GRID_OK={output_dir / filename} ({width}x{height})")

    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
    (WEB / "analysis-manifest.json").write_text(manifest_json, encoding="utf-8")
    (WEB / "analysis-manifest.generated.js").write_text(
        f"window.FROST_ANALYSIS_MANIFEST = {manifest_json};\n", encoding="utf-8"
    )
    print(f"ANALYSIS_MANIFEST_OK={WEB / 'analysis-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
