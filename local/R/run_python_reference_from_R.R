#!/usr/bin/env Rscript
# Launch the recommended Python implementation from an R workflow.
args <- commandArgs(trailingOnly = TRUE)
python <- Sys.getenv("FROST_PYTHON_BIN", unset = "python")
script <- file.path("local", "python", "frost_rf_local.py")
status <- system2(python, c(script, args), stdout = "", stderr = "")
if (status != 0) stop("Python reference workflow failed with exit code ", status)
message("R_TO_PYTHON_REFERENCE_OK")
