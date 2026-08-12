#!/usr/bin/env bash
#BSUB -J frost5_rf10k
#BSUB -q cnr
#BSUB -n 8
#BSUB -W 02:00
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=32GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_rf10k.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_rf10k.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/hpc/runtime_env.sh
"$FROST_PYTHON_BIN" "$FROST_MODULE/hpc_full_native_rf/scripts/prepare_runtime_config.py"
hand_path="$FROST_HPC_INPUT/anadem_rs_pr_sc_sp_ms_30m_HAND_flowpath_within_2000m_filled_zero.tif"
expected_hand_sha256="3b45aa4535119916ba76a9c8b0d0145e02d700489d606bc970a5a55f29f9901c"
actual_hand_sha256="$(sha256sum "$hand_path" | awk '{print $1}')"
[[ "$actual_hand_sha256" == "$expected_hand_sha256" ]] || {
  echo "HAND SHA-256 mismatch: expected=$expected_hand_sha256 actual=$actual_hand_sha256" >&2
  exit 1
}
echo "HPC_HAND_SHA256_OK=$actual_hand_sha256"
export FROST_SMOKE_OUTPUT="$FROST_MODULE/outputs/hpc_rf_reduced_10000_smoke"
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/34_hpc_rf_reduced_10000_smoke.py"
echo "HPC_RF_REDUCED_10000_SMOKE_OK"
