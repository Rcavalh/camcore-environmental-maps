#!/usr/bin/env Rscript
# Portable pure-R implementation of the three-endpoint frost Random Forest.

suppressPackageStartupMessages({
  library(ranger)
  library(data.table)
  library(jsonlite)
})

parse_args <- function(x) {
  out <- list()
  for (item in x) {
    if (!startsWith(item, "--") || !grepl("=", item, fixed = TRUE)) next
    pair <- strsplit(sub("^--", "", item), "=", fixed = TRUE)[[1]]
    out[[pair[1]]] <- paste(pair[-1], collapse = "=")
  }
  out
}

read_table <- function(path) {
  if (grepl("\\.parquet$", path, ignore.case = TRUE)) {
    if (!requireNamespace("arrow", quietly = TRUE)) stop("Install package 'arrow' for Parquet input")
    return(as.data.frame(arrow::read_parquet(path)))
  }
  as.data.frame(fread(path))
}

write_table <- function(x, path) {
  if (grepl("\\.parquet$", path, ignore.case = TRUE)) {
    if (!requireNamespace("arrow", quietly = TRUE)) stop("Install package 'arrow' for Parquet output")
    arrow::write_parquet(x, path)
  } else fwrite(x, path)
}

impute_fit <- function(x) vapply(x, function(v) median(v, na.rm = TRUE), numeric(1))
impute_apply <- function(x, medians) {
  for (name in names(medians)) x[[name]][is.na(x[[name]])] <- medians[[name]]
  x
}

auc_rank <- function(y, p) {
  positive <- p[y == 1]; negative <- p[y == 0]
  if (!length(positive) || !length(negative)) return(NA_real_)
  ranks <- rank(c(positive, negative), ties.method = "average")
  (sum(ranks[seq_along(positive)]) - length(positive) * (length(positive) + 1) / 2) /
    (length(positive) * length(negative))
}

pr_auc <- function(y, p) {
  ord <- order(p, decreasing = TRUE); y <- y[ord]
  tp <- cumsum(y == 1); fp <- cumsum(y == 0)
  recall <- tp / sum(y == 1); precision <- tp / pmax(tp + fp, 1)
  sum(diff(c(0, recall)) * precision)
}

classification_metrics <- function(y, p) {
  pred <- as.integer(p >= 0.5); tp <- sum(pred == 1 & y == 1); tn <- sum(pred == 0 & y == 0)
  fp <- sum(pred == 1 & y == 0); fn <- sum(pred == 0 & y == 1)
  sensitivity <- tp / max(tp + fn, 1); specificity <- tn / max(tn + fp, 1)
  precision <- tp / max(tp + fp, 1)
  data.frame(ROC_AUC = auc_rank(y, p), PR_AUC = pr_auc(y, p),
             balanced_accuracy = (sensitivity + specificity) / 2,
             sensitivity = sensitivity, specificity = specificity, precision = precision,
             F1 = 2 * precision * sensitivity / max(precision + sensitivity, 1e-12),
             Brier_score = mean((p - y)^2))
}

regression_metrics <- function(y, p) data.frame(
  RMSE = sqrt(mean((p - y)^2)), MAE = mean(abs(p - y)),
  R2 = 1 - sum((p-y)^2) / sum((y-mean(y))^2)
)

fit_model <- function(data, features, target, kind, trees, threads, seed) {
  if (kind == "classifier") data[[target]] <- factor(data[[target]], levels = c(0, 1))
  args <- list(dependent.variable.name = target, data = data[, c(features, target), drop = FALSE],
               num.trees = trees, mtry = max(1, floor(length(features) * 0.45)),
               min.node.size = 4, num.threads = threads, seed = seed,
               write.forest = TRUE, importance = "permutation")
  if (kind == "classifier") { args$probability <- TRUE; args$class.weights <- c("0"=1, "1"=1) }
  else args$splitrule <- if (kind == "poisson_regressor") "poisson" else "variance"
  do.call(ranger, args)
}

predict_endpoint <- function(model, data, kind) {
  p <- predict(model, data = data)$predictions
  if (kind == "classifier") p[, "1"] else as.numeric(p)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("training", "features", "output")
if (any(!required %in% names(args))) stop("Required: --training=... --features=... --output=...")
dir.create(args$output, recursive = TRUE, showWarnings = FALSE)
trees <- as.integer(ifelse(is.null(args$trees), 700, args$trees))
folds <- as.integer(ifelse(is.null(args$folds), 5, args$folds))
threads <- as.integer(ifelse(is.null(args$threads), max(1, parallel::detectCores()-1), args$threads))
seed <- as.integer(ifelse(is.null(args$seed), 20260807, args$seed)); set.seed(seed)
group_column <- ifelse(is.null(args$group_column), "station_id", args$group_column)

table <- read_table(args$training)
manifest <- fread(args$features); features <- manifest$feature
missing <- setdiff(features, names(table)); if (length(missing)) stop("Missing predictors: ", paste(head(missing,10),collapse=", "))
if (!is.null(args$quick_check) && nrow(table) > as.integer(args$quick_check)) table <- table[sample(nrow(table),as.integer(args$quick_check)),]
medians <- impute_fit(table[,features,drop=FALSE]); table[,features] <- impute_apply(table[,features,drop=FALSE],medians)
endpoints <- list(probability=c("frost_any","classifier"), frost_days=c("frost_days","poisson_regressor"), seasonal_tmin_c=c("observed_season_tmin_c","regressor"))
models <- list(); metric_rows <- list()

for (i in seq_along(endpoints)) {
  key <- names(endpoints)[i]; target <- endpoints[[i]][1]; kind <- endpoints[[i]][2]
  work <- table[!is.na(table[[target]]),,drop=FALSE]
  if (group_column %in% names(work) && length(unique(work[[group_column]])) >= folds) {
    groups <- unique(work[[group_column]]); fold_map <- setNames(sample(rep(seq_len(folds),length.out=length(groups))),groups)
    fold_id <- fold_map[as.character(work[[group_column]])]; validation <- "grouped"
  } else { fold_id <- sample(rep(seq_len(folds),length.out=nrow(work))); validation <- "random" }
  cvp <- rep(NA_real_,nrow(work))
  for (fold in seq_len(folds)) {
    train <- work[fold_id != fold,,drop=FALSE]; test <- work[fold_id == fold,,drop=FALSE]
    model <- fit_model(train,features,target,kind,trees,threads,seed+i+fold)
    cvp[fold_id == fold] <- predict_endpoint(model,test[,features,drop=FALSE],kind)
  }
  score <- if (kind == "classifier") classification_metrics(as.integer(work[[target]]),cvp) else regression_metrics(as.numeric(work[[target]]),cvp)
  metric_rows[[key]] <- cbind(endpoint=key,n=nrow(work),validation=validation,score)
  models[[key]] <- fit_model(work,features,target,kind,trees,threads,seed+i)
  message("LOCAL_R_ENDPOINT_OK=",key," n=",nrow(work)," validation=",validation)
}

bundle <- list(status="LOCAL_R_RF_THREE_ENDPOINTS_OK",features=features,medians=medians,
               endpoints=endpoints,models=models,seed=seed)
saveRDS(bundle,file.path(args$output,"frost_rf_three_endpoints.rds"),compress="xz")
fwrite(rbindlist(metric_rows,fill=TRUE),file.path(args$output,"validation_metrics_R.csv"))
write(toJSON(bundle[setdiff(names(bundle),"models")],pretty=TRUE,auto_unbox=TRUE),file.path(args$output,"model_contract_R.json"))

if (!is.null(args$prediction)) {
  pred <- read_table(args$prediction); pred[,features] <- impute_apply(pred[,features,drop=FALSE],medians)
  pred$predicted_frost_probability <- predict_endpoint(models$probability,pred[,features,drop=FALSE],"classifier")
  pred$predicted_frost_days <- pmax(0,predict_endpoint(models$frost_days,pred[,features,drop=FALSE],"poisson_regressor"))
  pred$predicted_seasonal_tmin_c <- predict_endpoint(models$seasonal_tmin_c,pred[,features,drop=FALSE],"regressor")
  write_table(pred,file.path(args$output,"predictions_R.csv"))
}
message("LOCAL_R_PIPELINE_OK=",normalizePath(args$output))
