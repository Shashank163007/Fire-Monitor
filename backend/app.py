"""Read-only FastAPI endpoints over a validated immutable retrospective snapshot."""
from collections import Counter
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import API_TITLE, API_VERSION, cors_origins
from .data_loader import Dataset, alert_key, load_dataset, numeric_summary
from .filters import AlertQuery, GroupQuery, HotspotQuery, ScientificFilters, applied, filter_hotspots, sort_hotspots
from .models import Alert, AlertGroup, Feature, FeatureCollection, GeoProperties, Health, Hotspot, Metadata, Page, Point, RiskDistribution, Statistics


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.dataset = load_dataset()
        yield

    application = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan,
                          description="Read-only June 2026 retrospective review data. No live feed, operational classifier or alert delivery.")
    application.add_middleware(CORSMiddleware,allow_origins=list(cors_origins()),allow_credentials=False,
                               allow_methods=["GET","OPTIONS"],allow_headers=["Accept"])

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        errors=[{"location":[str(v) for v in e['loc']],"message":e['msg'],"type":e['type']} for e in exc.errors()]
        return JSONResponse(status_code=422,content={"error":{"code":"validation_error","message":"Invalid request parameters","details":errors}})

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        code="not_found" if exc.status_code==404 else "method_not_allowed" if exc.status_code==405 else "request_error"
        return JSONResponse(status_code=exc.status_code,content={"error":{"code":code,"message":"Resource not found" if exc.status_code==404 else "Request not permitted"}},headers=exc.headers)

    @application.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse(status_code=500,content={"error":{"code":"internal_error","message":"Unable to serve request"}})

    @application.get("/api/v1/health",response_model=Health,summary="Check loaded demo dataset",description="Reports local snapshot readiness only, never external-feed connectivity.")
    def health(request: Request):
        data: Dataset=request.app.state.dataset
        return Health(service=API_TITLE,schema_version=data.manifest.schema_version,total_hotspots=len(data.hotspots))

    @application.get("/api/v1/meta",response_model=Metadata,summary="Describe retrospective scope and limitations",description="Provides the locked region/month, proxy-classification mode, review-score meaning and disclaimer.")
    def metadata(request: Request):
        m=request.app.state.dataset.manifest
        return Metadata(project_title=API_TITLE,dataset_mode=m.dataset_mode,geographic_bounds=m.region_bounds,period=m.period,
                        classification_source=m.classification_source,classifier_operational=m.classifier_operational,
                        scoring_method="Stage 5 fixed deterministic human-review priority; scores served unchanged",
                        total_hotspots=m.total_hotspots,class_counts=m.class_counts,risk_band_counts=m.risk_band_counts,
                        source_stage=m.generated_from_stage,data_disclaimer=m.disclaimer,limitations=m.limitations)

    @application.get("/api/v1/stats",response_model=Statistics,summary="Summarize all 674 detections",description="Counts and descriptive statistics over the loaded snapshot, without recalculating risk scores.")
    def statistics(request: Request):
        d=request.app.state.dataset
        return Statistics(total_hotspots=len(d.hotspots),class_counts=d.manifest.class_counts,risk_band_counts=d.manifest.risk_band_counts,
                          day_night_counts=dict(sorted(Counter(h.day_night for h in d.hotspots).items())),
                          confidence_counts=dict(sorted(Counter(h.confidence for h in d.hotspots).items())),
                          high_priority_alert_count=10,alert_group_count=len(d.alert_groups),
                          risk_score=numeric_summary(h.risk_score for h in d.hotspots),frp=numeric_summary(h.frp for h in d.hotspots),
                          persistence=numeric_summary(h.persistence_count_30d for h in d.hotspots))

    @application.get("/api/v1/hotspots",response_model=Page[Hotspot],summary="Filter and page thermal detections",description="Inclusive scientific filters; bbox is west,south,east,north. Deterministic sorting, limit 1–500, offset >=0. Empty matches return 200.")
    def hotspots(request: Request, query: Annotated[HotspotQuery,Query()]):
        selected=sort_hotspots(filter_hotspots(request.app.state.dataset.hotspots,query),query.sort_by,query.sort_order)
        items=tuple(selected[query.offset:query.offset+query.limit])
        return Page[Hotspot](items=items,total=len(selected),limit=query.limit,offset=query.offset,returned=len(items),applied_filters=applied(query),sort_by=query.sort_by,sort_order=query.sort_order)

    @application.get("/api/v1/hotspots.geojson",response_model=FeatureCollection,summary="Get filtered GeoJSON points",description="Same scientific filters as hotspots, without pagination. Coordinates are longitude,latitude; these are detections, not perimeters.")
    def geojson(request: Request, query: Annotated[ScientificFilters,Query()]):
        rows=sort_hotspots(filter_hotspots(request.app.state.dataset.hotspots,query))
        return FeatureCollection(features=tuple(Feature(geometry=Point(coordinates=(h.longitude,h.latitude)),properties=GeoProperties(**h.model_dump(include=set(GeoProperties.model_fields)))) for h in rows))

    @application.get("/api/v1/hotspots/{hotspot_id}",response_model=Hotspot,summary="Look up one detection by its stable ID",description="Opaque identifier lookup only; IDs never become filesystem paths. Unknown IDs return 404.")
    def detail(request: Request,hotspot_id: str):
        found=request.app.state.dataset.by_id.get(hotspot_id)
        if found is None: raise HTTPException(404)
        return found

    @application.get("/api/v1/alerts",response_model=Page[Alert],summary="Read the high-priority review queue",description="Only high/critical detections, ordered by score, persistence and FRP descending, then date/time/ID ascending. No alerts are sent.")
    def alerts(request: Request,query: Annotated[AlertQuery,Query()]):
        filters=ScientificFilters(**applied(query))
        selected=sorted((h for h in filter_hotspots(request.app.state.dataset.hotspots,filters) if h.risk_band in {'high','critical'}),key=alert_key)
        items=tuple(Alert(**h.model_dump(),alert_id='ALT-'+h.hotspot_id) for h in selected[query.offset:query.offset+query.limit])
        return Page[Alert](items=items,total=len(selected),limit=query.limit,offset=query.offset,returned=len(items),applied_filters=applied(query),sort_by="priority",sort_order="desc")

    @application.get("/api/v1/alert-groups",response_model=Page[AlertGroup],summary="Read preserved daily spatial summaries",description="Returns Stage 5 date/grid summaries unchanged. Cells are not incident boundaries; dates never merge.")
    def groups(request: Request,query: Annotated[GroupQuery,Query()]):
        selected=[g for g in request.app.state.dataset.alert_groups if (not query.date_from or g.acq_date>=query.date_from) and (not query.date_to or g.acq_date<=query.date_to)]
        items=tuple(selected[query.offset:query.offset+query.limit])
        return Page[AlertGroup](items=items,total=len(selected),limit=query.limit,offset=query.offset,returned=len(items),applied_filters=applied(query),sort_by="acq_date,grid_min_latitude,grid_min_longitude",sort_order="asc")

    @application.get("/api/v1/risk-distribution",response_model=RiskDistribution,summary="Get the Stage 5 class/band distribution",description="Includes zero-count combinations and explicitly labelled overall/all subtotals. Grand total 674; do not sum redundant subtotal rows.")
    def risk_distribution(request: Request):
        d=request.app.state.dataset
        return RiskDistribution(items=d.manifest.risk_distribution,total_hotspots=len(d.hotspots))

    return application


app=create_app()
