packages <- c("ranger", "data.table", "jsonlite", "terra", "arrow")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) install.packages(missing, repos = "https://cloud.r-project.org")
message("R_LOCAL_ENVIRONMENT_OK")
