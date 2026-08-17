#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5L) {
  stop("Usage: prepare_smoke_dem.R DEM.tif STUDY_AREA.shp OUTPUT.tif AUDIT.csv BUFFER_M")
}
suppressPackageStartupMessages(library(terra))

dem_path <- normalizePath(args[[1]], mustWork = TRUE)
study_path <- normalizePath(args[[2]], mustWork = TRUE)
output_path <- args[[3]]
audit_path <- args[[4]]
buffer_m <- suppressWarnings(as.numeric(args[[5]]))
if (!is.finite(buffer_m) || buffer_m < 15000) {
  stop("Smoke buffer must be at least 15,000 m for the 15-km flow-path test")
}
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(audit_path), recursive = TRUE, showWarnings = FALSE)

dem <- rast(dem_path)
study_native <- vect(study_path)
if (is.lonlat(dem)) {
  study_metric <- project(study_native, "EPSG:31982")
  smoke_boundary <- project(buffer(study_metric, width = buffer_m), crs(dem))
} else {
  smoke_boundary <- buffer(project(study_native, crs(dem)), width = buffer_m)
}
smoke_extent <- ext(smoke_boundary)
dem_extent <- ext(dem)
overlaps <- !(
  xmax(smoke_extent) <= xmin(dem_extent) || xmin(smoke_extent) >= xmax(dem_extent) ||
  ymax(smoke_extent) <= ymin(dem_extent) || ymin(smoke_extent) >= ymax(dem_extent)
)
if (!overlaps) stop("Pilot study area does not overlap the multi-state ANADEM")

smoke <- crop(dem, smoke_extent, snap = "out")
finite_cells <- global(ifel(is.na(smoke), 0, 1), "sum", na.rm = TRUE)[1, 1]
if (!is.finite(finite_cells) || finite_cells < 1000) {
  stop("Smoke DEM contains insufficient valid elevation cells")
}
writeRaster(
  smoke, output_path, overwrite = TRUE,
  wopt = list(datatype = "FLT4S", gdal = c("COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"))
)
audit <- data.frame(
  source_dem = dem_path, study_area = study_path,
  smoke_dem = normalizePath(output_path), buffer_m = buffer_m,
  requested_flowpath_radius_m = 15000,
  rows = nrow(smoke), columns = ncol(smoke), cells = ncell(smoke),
  finite_cells = finite_cells,
  grid_type = if (is.lonlat(smoke)) "geographic_sirgas2000_native" else "projected_metric_native",
  native_resolution_x = res(smoke)[1], native_resolution_y = res(smoke)[2],
  stringsAsFactors = FALSE
)
write.csv(audit, audit_path, row.names = FALSE)
cat("MULTISTATE_15000M_SMOKE_DEM_OK\n")
print(audit)
