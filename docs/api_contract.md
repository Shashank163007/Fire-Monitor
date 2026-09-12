# Stage 6 retrospective API contract, version 1.0.0

This API serves a retrospective demonstration dataset. Classes are rule-based weak-label categories, and risk scores rank detections for human review. They are not verified fire causes, probabilities, severity measurements or emergency-dispatch recommendations.

## Scope and runtime architecture

Serve June 1-30, 2026, 21 <= latitude < 24 and 72 <= longitude < 75. Exactly 674 detections have industrial/wildfire/unknown counts 308/79/287 and critical/high/moderate/low review-priority counts 0/10/149/515. Ten high-priority detections form six daily spatial summaries. All class probabilities are JSON null. Classification source is `rule_based_weak_label_fallback`; neither Stage 4 model is operational or loaded. No score or classification is recalculated.

The backend package contains app.py (routes and lifespan), config.py (fixed scope/source provenance and CORS), data_loader.py (strict snapshot validation), filters.py (validated queries and pure filtering), and models.py (Pydantic data/response contracts, not trained classifiers). A forwarding-only services layer is unnecessary. There is no database, authentication, background worker, external alert sender or visual frontend.

Startup reads only the three module-relative backend/data JSON files, validates them, and stores frozen Pydantic records in tuples plus a read-only ID index. Nested manifest counts, hash records and distribution rows are frozen. Loading does not depend on the working directory, src/, raw files, caches, processed outputs or model binaries. Missing files, malformed JSON, duplicate keys, nonfinite numbers, hash inconsistencies, invalid types, counts, scope, grouping or distribution stop startup clearly. No endpoint permits a data path parameter. Requests filter/sort new lists without mutating shared records and perform no data-file reads.

## Tracked snapshot and provenance

`src/export_demo_data.py` authenticates all five Stage 5 CSVs against their locked SHA-256 values before parsing. The classified source must have SHA-256 `29031a9049f145574c507fba40e6d94b3760052e2d199287d3934d2733b614cf`. All source schemas, audit joins/order, alert fields/order, group membership and distribution are validated without repairing rows or invoking either preceding pipeline.

- demo_hotspots.json: 674 records in exactly the classified CSV's order. Each contains the requested 23 frontend-safe fields, including classification_source, null probability, component points, primary driver and unchanged explanation. Internal query flags, nearest mining audit details, weak-label reasons and model features not requested for the frontend are excluded.
- demo_alert_groups.json: the six original Stage 5 summaries, with unchanged IDs, explanations, values and date/grid order. Membership counts reconcile with the ten high-priority detections; no group crosses a date.
- demo_manifest.json: schema_version 1.0.0, generated_from_stage 5, dataset_mode retrospective_demo, classifier_operational false, scope, counts, source/export hashes, limitations and the exact disclaimer. The existing 20-row Stage 5 risk distribution is retained in `risk_distribution` so runtime requires no fourth file or ignored CSV.

The manifest stores source and exported hashes as ordered arrays of `{filename, sha256}` records. It hashes only demo_hotspots.json and demo_alert_groups.json; its own hash is calculated externally and recorded in stage6_validation.md. It uses `generated_at_policy: omitted_for_deterministic_export` and no current timestamp. JSON is compact UTF-8 with stable Pydantic field order and one trailing LF. Numeric source values convert to JSON numbers without additional rounding; confidence, classes, IDs, explanations and zero-padded HHMM remain strings. Audit points preserve source precision up to 12 decimal places; scores preserve their two-decimal numeric values (JSON may omit trailing zeroes). Empty cells become JSON null only where permitted. JSON NaN/Infinity and duplicate keys are rejected.

backend/data/.gitattributes assigns text eol=lf to exactly the three JSON filenames. This new, narrow configuration is necessary because Windows Git autocrlf would otherwise convert checkout bytes and invalidate the manifest's hashes after cloning. It changes no earlier file or general data-directory tracking rule.

Export computes and validates all bytes first, then atomically replaces each of the three fixed destination files. Atomicity is per file, not a three-file transaction; an interrupted export may leave a hash mismatch and startup will fail until a valid rerun. Earlier-stage files are read-only. Hash validation detects inconsistency, not authenticity against a malicious editor who can change both code and manifest. Git history supplies checkpoint provenance.

## Endpoints

API prefix: `/api/v1`. The explicit application title is `Fire Monitor Retrospective Review API`, version `1.0.0`. `/openapi.json`, `/docs` and `/redoc` remain enabled.

| GET endpoint | Response |
| --- | --- |
| /health | status=ok, service, schema_version, dataset_loaded=true, total_hotspots=674. Local snapshot readiness only. |
| /meta | Project title, retrospective mode, geographic bounds, period, classification source/status, scoring method, counts, source stage, disclaimer and limitations. |
| /stats | Global class/band, D/N and l/n/h counts; ten alerts/six groups; minimum/median/mean/maximum of stored risk scores, FRP and persistence. |
| /hotspots | Filtered, sorted and paginated complete frontend-safe hotspot records. |
| /hotspots/{hotspot_id} | One complete record; opaque ID lookup, never a filesystem path. Missing IDs return 404. |
| /hotspots.geojson | Filtered Point FeatureCollection, without pagination. Coordinates are [longitude, latitude]. |
| /alerts | High/critical hotspot records with ALT- prefixed alert_id, filtered and paginated in Stage 5 priority order. Nothing is transmitted. |
| /alert-groups | Original Stage 5 daily spatial summaries, date-filtered and paginated. No reinterpretation as incident boundaries. |
| /risk-distribution | `{items, total_hotspots}` containing the existing 20 distribution rows and total 674. |

Descriptive statistics operate on the loaded snapshot and round median/mean half-even to two decimals; minima/maxima retain source precision. This aggregates stored scores rather than recomputing their formula. Empty Stage 5 distribution combinations have null statistics. Distribution ordering is industrial, wildfire, unknown, overall; within each class: critical, high, moderate, low, all. `all` and `overall` are explicitly labelled subtotals, not extra detections; do not add them to the non-subtotal counts.

GeoJSON properties contain hotspot_id, acq_date, acq_time, predicted_class, classification_source, frp, persistence_count_30d, risk_score, risk_band, day_night, confidence, primary_risk_driver and explanation. GeoJSON ordering is date, time, ID ascending. Coordinates represent thermal detections, not measured fire perimeters.

## Strict scientific filters and pagination

/hotspots and /hotspots.geojson accept:

| Parameter | Validation and meaning |
| --- | --- |
| predicted_class | One lowercase industrial, wildfire or unknown. |
| risk_band | One lowercase critical, high, moderate or low. |
| date_from, date_to | Exact ISO YYYY-MM-DD; inclusive date limits. Out-of-study valid dates can produce empty results; reversed ranges are invalid. |
| day_night | Exactly D or N, matching source values. |
| min_frp, max_frp | Finite nonnegative MW; inclusive limits. |
| min_risk_score, max_risk_score | Finite values within [0,100]; inclusive limits. |
| min_persistence | Integer in [1,30], inclusive minimum. |
| bbox | Four finite numbers in min_longitude,min_latitude,max_longitude,max_latitude order. WGS84 bounds, positive width/height, inclusive query edges. |

Every supplied condition is combined with AND. Empty, unsupported, nonfinite or reversed filter values return 422. Undeclared query parameters are rejected. Only /hotspots also accepts `sort_by`, `sort_order`, `limit` and `offset`; GeoJSON rejects pagination/sort parameters and uses the fixed default order.

Allowed sort_by: acq_date, acq_time, frp, persistence_count_30d, risk_score, predicted_class, risk_band, hotspot_id. Default acq_date ascending retains acq_time then hotspot_id ascending. For any selected primary field, ties use date/time/ID ascending, even with descending primary order. Risk-band sorting uses severity low < moderate < high < critical; class sorting is alphabetical. Other fields use their natural numeric/string ordering. sort_order is asc or desc.

All paginated endpoints default limit=100, permit integer limits 1-500 and nonnegative offset=0. Envelope: `{items, total, limit, offset, returned, applied_filters, sort_by, sort_order}`. total is the filtered count before pagination. Offset beyond the end returns 200 with items=[], returned=0. applied_filters excludes pagination/sort settings and omitted values.

/alerts accepts only date_from, date_to, predicted_class, limit and offset. Its fixed priority order is score descending, persistence descending, FRP descending, date ascending, time ascending, ID ascending. Envelope sort_by is `priority`, sort_order desc, documenting this compound ordering rather than allowing it to be changed. /alert-groups accepts only date_from, date_to, limit and offset, retaining acquisition date, minimum latitude and minimum longitude order.

## Errors, CORS and local operation

Unknown resource: HTTP 404, `{"error":{"code":"not_found","message":"Resource not found"}}`. Invalid query: HTTP 422 with `error.code=validation_error`, a fixed message and sanitized details containing location/message/type only. Unsupported methods return 405 and the same error envelope family. Unexpected server errors return a generic 500 body, never a Python stack trace or local file contents. Startup validation errors remain operator-facing and stop serving. Standard CORS middleware rejects invalid preflights with 400 and no allow-origin header; these middleware responses use Starlette's standard text body.

Default CORS origins are exactly http://localhost:5173 and http://127.0.0.1:5173. FIRE_MONITOR_CORS_ORIGINS optionally appends comma-separated explicit HTTP(S) origins. Wildcards, credentials, paths, query strings and fragments in origins are rejected. Credentials are false, allowed methods GET/OPTIONS, and only Accept plus browser CORS-safelisted headers are allowed. No secrets or environment files are required. Binding defaults in the README to 127.0.0.1 limits local development exposure.

HTTPX TestClient calls use in-process ASGI transport and open no network connections. On Windows, asyncio's `_fallback_socketpair` creates a loopback wakeup channel; validation permits only that specific standard-library IPC call and blocks other connects and network HTTP transports. Local Uvicorn startup is tested separately without sending socket-based requests. Browser Swagger UI HTML uses FastAPI's standard external CDN assets; the API and /openapi.json work offline, while loading that browser UI may need cached assets or internet. No browser/CDN requests are made during Stage 6 validation.

Use wording such as `Retrospective June 2026 review queue`, `Rule-based context category: industrial` and `Review priority: high`. Never describe high priority as a verified emergency or the classification as verified cause. Routine industrial heat can rank highly, low priority does not establish safety, persistence includes same-date later detections, and source geolocation/coverage and static OSM/WorldCover context limit interpretation. No visual frontend or Stage 7 work is included.
