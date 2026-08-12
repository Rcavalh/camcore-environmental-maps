#!/usr/bin/env Rscript
# Predict native-grid outputs from aligned GeoTIFF covariates using a pure-R model bundle.
suppressPackageStartupMessages(library(terra))

parse_args <- function(x){out<-list();for(item in x){if(startsWith(item,"--")&&grepl("=",item,fixed=TRUE)){p<-strsplit(sub("^--","",item),"=",fixed=TRUE)[[1]];out[[p[1]]]<-paste(p[-1],collapse="=")}};out}
args<-parse_args(commandArgs(trailingOnly=TRUE))
if(any(!c("model","covariates","output")%in%names(args)))stop("Required: --model=... --covariates=... --output=...")
bundle<-readRDS(args$model);dir.create(args$output,recursive=TRUE,showWarnings=FALSE)
paths<-file.path(args$covariates,paste0(bundle$features,".tif"));missing<-paths[!file.exists(paths)]
if(length(missing))stop("Missing covariate rasters: ",paste(head(missing,5),collapse=", "))
x<-rast(paths);names(x)<-bundle$features
prediction_fun<-function(model,data,endpoint){for(n in model$features)data[[n]][is.na(data[[n]])]<-model$medians[[n]];kind<-model$endpoints[[endpoint]][2];predict_endpoint(model$models[[endpoint]],data[,model$features,drop=FALSE],kind)}
predict_endpoint<-function(model,data,kind){p<-predict(model,data=data)$predictions;if(kind=="classifier")p[,"1"]else as.numeric(p)}
writeRaster(predict(x,bundle,fun=function(model,data)prediction_fun(model,data,"probability")),file.path(args$output,"RF_FROST_OCCURRENCE_PROBABILITY.tif"),overwrite=TRUE,gdal=c("COMPRESS=DEFLATE","BIGTIFF=YES"))
writeRaster(predict(x,bundle,fun=function(model,data)pmax(0,prediction_fun(model,data,"frost_days"))),file.path(args$output,"RF_EXPECTED_FROST_DAYS.tif"),overwrite=TRUE,gdal=c("COMPRESS=DEFLATE","BIGTIFF=YES"))
writeRaster(predict(x,bundle,fun=function(model,data)prediction_fun(model,data,"seasonal_tmin_c")),file.path(args$output,"RF_SEASONAL_MINIMUM_TEMPERATURE_C.tif"),overwrite=TRUE,gdal=c("COMPRESS=DEFLATE","BIGTIFF=YES"))
message("LOCAL_R_RASTER_PREDICTION_OK=",normalizePath(args$output))
