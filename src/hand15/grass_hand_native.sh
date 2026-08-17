#!/usr/bin/env bash
# Native-grid HAND driver for GRASS GIS 8.x.
set -euo pipefail

usage() {
  echo "Usage: $0 --dem DEM.tif --output-dir DIR --label LABEL [--hydro rivers.shp] [--stream-area-km2 1 | --stream-threshold-cells 50000] [--memory-mb 64000]" >&2
}

dem=""; hydro=""; output_dir=""; label=""; stream_area_km2="1"; stream_threshold_cells=""; memory_mb="64000"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dem) dem="$2"; shift 2 ;;
    --hydro) hydro="$2"; shift 2 ;;
    --output-dir) output_dir="$2"; shift 2 ;;
    --label) label="$2"; shift 2 ;;
    --stream-area-km2) stream_area_km2="$2"; shift 2 ;;
    --stream-threshold-cells) stream_threshold_cells="$2"; shift 2 ;;
    --memory-mb) memory_mb="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ -n "$dem" && -n "$output_dir" && -n "$label" ]] || { usage; exit 2; }
[[ "$label" =~ ^[A-Za-z0-9_]+$ ]] || { echo "Label may contain only letters, numbers, and underscore." >&2; exit 2; }
[[ -f "$dem" ]] || { echo "DEM not found: $dem" >&2; exit 2; }
if [[ -n "$hydro" && ! -f "$hydro" ]]; then echo "Hydrography not found: $hydro" >&2; exit 2; fi

grass_bin="${GRASS_BIN:-$(command -v grass || true)}"
[[ -n "$grass_bin" ]] || { echo "GRASS executable not found. Activate the grass-hand environment." >&2; exit 2; }
script_dir="$(cd "$(dirname "$0")" && pwd)"
worker="${script_dir}/grass_hand_worker.sh"
[[ -f "$worker" ]] || { echo "Worker not found: $worker" >&2; exit 2; }

mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
dem="$(cd "$(dirname "$dem")" && pwd)/$(basename "$dem")"
if [[ -n "$hydro" ]]; then hydro="$(cd "$(dirname "$hydro")" && pwd)/$(basename "$hydro")"; fi
work_root="${TMPDIR:-${output_dir}/grass_work}"
mkdir -p "$work_root"
run_root="$(mktemp -d "${work_root%/}/grass_hand_${label}_XXXXXX")"
location="${run_root}/grassdata/native"
mkdir -p "$(dirname "$location")"
cleanup() {
  if [[ "${HAND_KEEP_GRASS_WORK:-0}" != "1" && -d "$run_root" ]]; then
    rm -rf -- "$run_root"
  fi
}
trap cleanup EXIT

export HAND_DEM="$dem" HAND_HYDRO="$hydro" HAND_OUTPUT_DIR="$output_dir"
export HAND_LABEL="$label" HAND_STREAM_AREA_KM2="$stream_area_km2" HAND_MEMORY_MB="$memory_mb"
export HAND_STREAM_THRESHOLD_CELLS="$stream_threshold_cells"
if [[ -n "$stream_threshold_cells" && "$stream_threshold_cells" =~ ^[0-9]+$ ]] && \
   (( stream_threshold_cells % 1000 == 0 )); then
  export HAND_THRESHOLD_TAG="$((stream_threshold_cells / 1000))k"
else
  export HAND_THRESHOLD_TAG="${stream_threshold_cells:-area}"
fi
export HAND_PROXY_RADII_M="${HAND_PROXY_RADII_M:-500 1000 1500 2000 10000}"
export HAND_FLOWPATH_RADII_M="${HAND_FLOWPATH_RADII_M:-500 1000 2000 10000}"
for radius in $HAND_FLOWPATH_RADII_M; do
  [[ "$radius" =~ ^[1-9][0-9]*$ ]] || {
    echo "Invalid HAND flow-path radius: $radius" >&2
    exit 2
  }
done
# The production jobs reproduce the two commands supplied by the student.
# Optional experimental hydrography/proxy behavior must be requested explicitly.
export HAND_STUDENT_EXACT="${HAND_STUDENT_EXACT:-1}"

"$grass_bin" -c "$dem" "$location" --exec bash "$worker"
echo "GRASS_HAND_NATIVE_OK label=${label} output=${output_dir}"
