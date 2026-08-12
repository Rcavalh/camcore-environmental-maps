# Bioclimatic Variables collection

## Scope

The portal exposes 19 standard BIOCLIM variables derived for the 1981–2025 climate period. Temperature inputs come from TerraClimate and precipitation inputs from CHIRPS. The source grids have a nominal 2.5-arc-minute resolution (8,640 × 4,320 cells).

## Variable groups

- **Temperature (BIO1–BIO11):** annual means, thermal ranges, seasonality, monthly extremes and quarter-based summaries.
- **Precipitation (BIO12–BIO19):** annual total, monthly and quarterly extremes, and precipitation seasonality.

The exact variable name and physical unit are shown in the map interface. Temperature variables are expressed in degrees Celsius except BIO3 (percent) and BIO4 (standard deviation × 100). Precipitation variables are expressed in millimetres except BIO15 (coefficient of variation, percent).

## Data-quality treatment

Negative finite sentinels inherited from missing monthly precipitation inputs are treated as NoData in BIO12, BIO13, BIO14, BIO16, BIO17, BIO18 and BIO19. Negative temperatures remain valid. The source rasters are not spatially smoothed.

## Portal rendering

Each web preview is created from the source raster at its native horizontal grid width and reprojected for Leaflet display. A viridis-derived yellow-to-blue palette is applied independently to each variable: yellow represents lower values and blue represents higher values. To prevent a small number of extremes from obscuring spatial structure, colors use the 2nd–98th percentile display range. The scientific values remain unchanged in the numerical inspection grid and GeoTIFF products.

The portal supports point inspection, rectangle or polygon summaries, CSV/GeoJSON export, map/satellite basemaps, location search and full-screen viewing.

## Distribution strategy

GitHub Pages stores optimized interactive assets. Native GeoTIFFs are intended for a persistent research-data repository because they are substantially larger and are the authoritative files for quantitative analysis.

## Core sources

- Abatzoglou, J. T., Dobrowski, S. Z., Parks, S. A. & Hegewisch, K. C. TerraClimate, a high-resolution global dataset of monthly climate and climatic water balance from 1958–2015. *Scientific Data* **5**, 170191 (2018). https://doi.org/10.1038/sdata.2017.191
- Funk, C. et al. The climate hazards infrared precipitation with stations—a new environmental record for monitoring extremes. *Scientific Data* **2**, 150066 (2015). https://doi.org/10.1038/sdata.2015.66
