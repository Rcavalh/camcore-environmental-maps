# Web map

This bilingual static portal presents five map collections: frost climatology, species
suitability, bioclimatic variables, monthly heat maps and Camcore tested provenances.
The frost layer menu is organized into three compact groups:

- complete period (2000–2026, version 2.0): probability, expected frost days, mean seasonal minimum
  temperature and the lower-tail P25 seasonal minimum temperature;
- ENSO phases: probability and P25 seasonal minimum temperature for
  El Niño, La Niña and neutral seasons;
- terrain: HAND derived with 2-km and 15-km flow-path limits, plus ANADEM elevation.

It includes dark and light themes, an offline list of key cities, and online fallback
geocoding for other Brazilian locations.

Rebuild the high-definition web previews and both metadata catalogs:

```bash
python src/portal/build_web_layers.py
python src/portal/build_analysis_grids.py --width 2048
```

The raster collections support point-value inspection, rectangle, circle and polygon selection,
area summaries, histograms, and CSV/GeoJSON export. These interactive summaries
use quantized numerical web grids aligned with the map previews. Native-resolution
analysis and analytical clipping must use the downloadable GeoTIFFs.

All PNG overlays and numerical web grids are reprojected to EPSG:3857 before
publication so that internal raster features align with the Leaflet basemap. The
downloadable analytical GeoTIFFs retain their native SIRGAS 2000 grid.
Pixels intersecting Lagoa dos Patos are masked from the PNG overlays and numerical
web grids using the stored OpenStreetMap water polygon (relation 2709093). Source
GeoTIFFs are not modified.

The map can be opened directly from `web/index.html`. For the closest match to GitHub Pages, preview it from the repository root:

```bash
python -m http.server 8000 --directory web
```

Then open `http://localhost:8000`. The analytical GeoTIFFs are not embedded in the website; the PNGs are visualization derivatives only.

The authoritative 2000–2026 Frost Climatology GeoTIFF collection and supporting metadata are archived on Zenodo: [https://doi.org/10.5281/zenodo.21981334](https://doi.org/10.5281/zenodo.21981334).

Additional collection builders:

```bash
python src/portal/build_heat_previews.py --web web
python src/portal/build_provenance_catalog.py --source CamcoreProvs.csv --web web
```
