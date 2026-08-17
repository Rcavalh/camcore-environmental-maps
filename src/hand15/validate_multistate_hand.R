#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5L) {
  stop("Usage: validate_multistate_hand.R DEM OUTPUT_DIR LABEL RADII_CSV MARKER_NAME")
}
suppressPackageStartupMessages(library(terra))

dem_path <- normalizePath(args[[1]], mustWork = TRUE)
out_dir <- normalizePath(args[[2]], mustWork = TRUE)
label <- args[[3]]
radii <- suppressWarnings(as.integer(strsplit(args[[4]], ",", fixed = TRUE)[[1]]))
marker_name <- args[[5]]
if (!length(radii) || any(!is.finite(radii)) || any(radii <= 0)) stop("Invalid radii")

dem <- rast(dem_path)
files <- sprintf("%s_HAND_flowpath_within_%dm.tif", label, radii)
missing <- files[!file.exists(file.path(out_dir, files))]
if (length(missing)) stop("Missing requested HAND rasters: ", paste(missing, collapse = ", "))

read_stats <- function(radius, file) {
  x <- rast(file.path(out_dir, file))
  if (!compareGeom(dem, x, stopOnError = FALSE, crs = TRUE, ext = TRUE,
                   rowcol = TRUE, res = TRUE)) stop("Geometry differs from source DEM: ", file)
  if (datatype(x) != "FLT8S") stop("Expected Float64 HAND output: ", file)
  stats_path <- file.path(out_dir, sprintf("%s_HAND_flowpath_within_%dm_stats.txt", label, radius))
  if (!file.exists(stats_path)) stop("Missing GRASS statistics: ", stats_path)
  lines <- readLines(stats_path, warn = FALSE)
  pieces <- strsplit(lines[grepl("=", lines, fixed = TRUE)], "=", fixed = TRUE)
  values <- setNames(vapply(pieces, function(z) paste(z[-1], collapse = "="), character(1)),
                     vapply(pieces, `[[`, character(1), 1L))
  number <- function(key) suppressWarnings(as.numeric(values[[key]]))
  data.frame(variant = "masked", radius_m = radius, file = file, finite_cells = number("n"),
             minimum_m = number("min"), mean_m = number("mean"), maximum_m = number("max"))
}
masked_audit <- do.call(rbind, Map(read_stats, radii, files))
masked_audit <- masked_audit[order(masked_audit$radius_m), ]
if (any(!is.finite(masked_audit$finite_cells)) || any(masked_audit$finite_cells < 1)) {
  stop("At least one requested HAND raster has no finite cells")
}
if (any(diff(masked_audit$finite_cells) < 0)) {
  stop("HAND support must not shrink when the flow-path radius increases")
}
audit <- masked_audit
if (identical(Sys.getenv("HAND_EXPORT_FILLED_ZERO", "0"), "1")) {
  filled_files <- sprintf("%s_HAND_flowpath_within_%dm_filled_zero.tif", label, radii)
  missing_filled <- filled_files[!file.exists(file.path(out_dir, filled_files))]
  if (length(missing_filled)) {
    stop("Missing requested filled-zero HAND rasters: ", paste(missing_filled, collapse = ", "))
  }
  read_filled_stats <- function(radius, file) {
    x <- rast(file.path(out_dir, file))
    if (!compareGeom(dem, x, stopOnError = FALSE, crs = TRUE, ext = TRUE,
                     rowcol = TRUE, res = TRUE)) stop("Geometry differs from source DEM: ", file)
    if (datatype(x) != "FLT8S") stop("Expected Float64 filled-zero HAND output: ", file)
    stats_path <- file.path(
      out_dir,
      sprintf("%s_HAND_flowpath_within_%dm_filled_zero_stats.txt", label, radius)
    )
    if (!file.exists(stats_path)) stop("Missing filled-zero GRASS statistics: ", stats_path)
    lines <- readLines(stats_path, warn = FALSE)
    pieces <- strsplit(lines[grepl("=", lines, fixed = TRUE)], "=", fixed = TRUE)
    values <- setNames(vapply(pieces, function(z) paste(z[-1], collapse = "="), character(1)),
                       vapply(pieces, `[[`, character(1), 1L))
    number <- function(key) suppressWarnings(as.numeric(values[[key]]))
    data.frame(
      variant = "filled_zero", radius_m = radius, file = file,
      finite_cells = number("n"), minimum_m = number("min"),
      mean_m = number("mean"), maximum_m = number("max")
    )
  }
  filled_audit <- do.call(rbind, Map(read_filled_stats, radii, filled_files))
  if (any(!is.finite(filled_audit$finite_cells)) || any(filled_audit$finite_cells < 1)) {
    stop("At least one filled-zero HAND raster has no finite cells")
  }
  if (any(!is.finite(filled_audit$minimum_m)) || any(filled_audit$minimum_m < 0)) {
    stop("Filled-zero HAND rasters contain negative values")
  }
  audit <- rbind(masked_audit, filled_audit)
}
write.csv(audit, file.path(out_dir, sprintf("%s_requested_radii_validation.csv", label)), row.names = FALSE)
writeLines(
  c(marker_name, paste0("dem=", dem_path), paste0("radii_m=", paste(radii, collapse = ","))),
  file.path(out_dir, marker_name)
)
cat(marker_name, "\n", sep = "")
print(audit)
