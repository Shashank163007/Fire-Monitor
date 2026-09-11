# Classifier feature policy and Stage 3.6 evaluation

This policy applies to the two-class industrial/wildfire scope. Stage 3.6 only evaluates readiness and exports training candidates; it does not train a model or create final predictions. All labels remain proxies, not verified fire causes. The locked final output field contract is unchanged.

## Direct proxy-label source features

| Feature | Role in label construction |
| --- | --- |
| distance_to_industrial_km | Tests industrial proximity within 1 km or no mapped industrial object within 1 km |
| land_cover_code | Numeric centre-pixel WorldCover class underlying the land-cover predicates |
| land_cover_class | Centre Tree cover/Shrubland/Cropland predicates and industrial water exclusion |
| nearest_mine_or_quarry_distance_km | Mining proximity exclusion and industrial/mining conflict detection |

A model containing these direct label-source features measures reproduction of the weak-label rules. Its score must be reported as **weak-label agreement**, not **accuracy**. A random split does not remove this target leakage. Codes and names are redundant encodings of the same label source. Nominal-footprint land-cover summaries, query flags, object counts, core-cell IDs and derived proximity flags can also reveal the label sources; they are not independent ablation inputs.

## Independent FIRMS-derived features

| Feature | Meaning |
| --- | --- |
| frp | Observed fire radiative power |
| brightness | Native brightness temperature |
| bright_t31 | Native companion thermal-band brightness temperature |
| confidence | VIIRS categorical detection confidence, not a class probability |
| day_night | D/N observation flag |
| persistence_count_30d | Distinct detection dates in the same 0.01-degree cell during [date-29,date] |
| scan | Native across-scan pixel dimension |
| track | Native along-track pixel dimension |

A later **ablation model using only these eight independent FIRMS-derived features is required**. Here independent means not directly used to generate the proxy labels; it does not imply statistical independence, independent events, or causal evidence. Neither the direct-source model nor the ablation model yields verified real-world fire-cause accuracy. Both must be evaluated as weak-label agreement, with spatial/temporal dependence discussed. No model was trained in Stage 3.6.

hotspot_id, coordinates, acquisition date/time, satellite, instrument and core_osm_cell_id remain audit/provenance or split-design fields. They are not extra inputs to the required eight-feature ablation. Retain zero-padded HHMM times. No weak_label, weak_label_reason, weak_label_source, weak_label_conflict, context_available or eligibility field may be a model input. Later train/test partitioning must consider repeated spatial sources and dates; a row-level random split can share the same source across partitions.

## Expanded region, history and raster boundaries

The study is exactly 21 <= latitude < 24 and 72 <= longitude < 75, targeting June 1-30, 2026. Nine one-degree core cells partition this region with south/west inclusion and north/east exclusion. Every target is assigned once. The nine buffered query boxes are context areas only; they never add target rows. Points at 24 N or 75 E are excluded.

Persistence reuses the earlier distinct-date implementation with all available normalized history from May 1-June 30. Its inclusive window [d-29,d] contains exactly 30 calendar dates; June 1 begins May 3. Multiple detections per cell/date count once. No pre-May observations are invented. Completeness is calendar-range availability, not proof of a valid satellite observation every day. All same-date detections can contribute retrospectively, including observations later than the target row's acquisition time.

The existing official ESA WorldCover 2021 v200 N21E072 Map COG is checked against its manifest checksum/size, CRS, band, resolution and bounds before processing. It covers the complete study rectangle. No additional tile is needed. The existing north-up raster sampler treats its exact south edge as outside; the new Stage 3.6 wrapper handles the included 21 N study boundary by sampling the immediately adjacent interior pixel with an inward shift below 0.00001 m. This avoids changing any older function or historical output. Exact north/east study boundaries remain excluded.

land_cover_class remains the centre-pixel class, with its numeric land_cover_code preserved. Unknown/nodata is unavailable context and precedes every label rule. The existing nominal 390 m window remains audit-only; it approximates a VIIRS detection scale, not an actual fire boundary. Pixel proportions use valid pixels, and edge clipping remains explicitly flagged. WorldCover 2021 may not reflect 2026 land cover.

## Buffered OSM acquisition, caching and merged distances

Each core query is expanded by 0.02 degrees on all sides. For example cell_21_72 queries (20.98,71.98,22.02,73.02), and cell_23_74 queries (22.98,73.98,24.02,75.02), in south/west/north/east order. At these latitudes this buffer exceeds the 1 km proximity threshold. Outer queries intentionally extend beyond the display/study region.

Only the free Overpass endpoint and the existing industrial/mining tag definitions are used, without paid services or keys. Cached responses are reused only if the endpoint/query hash, response SHA-256, byte size, valid response structure, required selectors and buffered query coverage pass validation. Earlier unbuffered one-degree Stage 2.5 queries fail this area requirement. Compatible larger queries can be reused. Each missing query has at most three attempts with exponential backoff (2 and 4 seconds). Raw HTTP bodies, including errors, are saved unchanged before parsing. No dummy substitution exists.

Each core has a separate manifest; the aggregate manifest lists all nine. They record core bounds, actual buffered query bounds, endpoint, exact query, query hash (SHA-256 of endpoint concatenated with query), status, raw filename/size/SHA-256, request outcomes and feature counts. Initial acquisition provenance stays constant on cache reuse. Operational cache-hit counts appear in stdout and do not change deterministic outputs. `--offline` requires existing per-cell manifests, preserves failed-query status and makes no network requests. Failed cells remain context-unavailable even when adjacent query responses cover part of the cell.

Objects merge by (OSM type, OSM ID), with a stable alphabetical core-cell order. Identical IDs retrieved multiple times are deduplicated; conflicting snapshots of the same ID retain the first cell's object and are counted in the report. Overlapping ways and relations with different IDs remain distinct. Stage 2's geometry conversion, mine tagging and mining-overlap exclusions are reused. Unsupported geometry is reported; failed reconstruction never means that an object is absent.

Every nearest distance uses the **complete merged deduplicated** industrial/mining feature collection, not just the assigned cell's response. The method remains WGS84 ellipsoidal distance to nearest geometry through a hotspot-centred AEQD projection with densified polygon edges. It is not a centroid or degree-distance approximation; polygon nearest-point placement remains a documented numerical approximation.

The audit's mapped_industrial_object_count and mapped_mining_object_count describe usable objects from the row's core query. Thus a core count can be zero while its globally nearest distance is finite to an object retrieved outside that query. If no merged object exists, distance is missing; successful query flags and zero mapped-object counts distinguish this from failure. Failed queries set both success flags false. Neither a successful empty query nor no object within 1 km proves real-world absence. Query buffers also cannot guarantee finding an enclosing polygon with no vertex inside the query area.

## Exact Stage 3.6 weak-label priority

1. unknown_context_unavailable: required OSM or centre-pixel WorldCover context is invalid/unavailable.
2. conflict_excluded: industrial and mining distances are both <=1 km.
3. industrial_candidate: industrial <=1 km, no mapped mining within 1 km, and valid centre class is not Permanent water bodies.
4. wildfire_candidate: centre Tree cover or Shrubland, no mapped industrial within 1 km, and no mapped mining within 1 km.
5. cropland_hotspot_candidate: centre Cropland with no mapped industrial/mining within 1 km; contextual audit evidence only.
6. unknown: every remaining row.

The no-mapped-object predicates require successful OSM queries. This Stage 3.6 request explicitly allows successful-empty context for those predicates; a failed query is never treated as empty. Cropland is never called an agricultural burn; no regional burning-season calendar is invented. No flare label or VNF matches are created. VNF remains an optional blocked source pending a separate licence/application.

## Training candidates and readiness

The candidate CSV contains only industrial_candidate and wildfire_candidate rows with valid required FIRMS fields, valid WorldCover centre context, successful valid OSM context, complete persistence history, and no conflict. Native numeric features must be finite; FRP is nonnegative and brightness/bright_t31/scan/track are positive. Required categorical values and acquisition-time formatting must be valid. Missing native measurements remain in the audit and are excluded from this training-candidate pool. No rows are balanced, oversampled, undersampled or synthesized. weak_label remains in the CSV for auditability.

Apply the nine Stage 3.6 requirements exactly: >=20 rows in each class, >=50 total, neither class above 90%, all eligible OSM valid, all eligible WorldCover valid, >=80% complete history, no conflicts, and unique hotspot IDs. Percentages use the training-candidate pool. Balance ratio is larger class / smaller class; if either count is zero, the ratio is null and readiness is false. Complete history is already required for candidate export, so a nonempty candidate pool has 100% complete history; whole-audit completeness is reported separately. The Stage 3.5 monthly-concentration rule is not part of this explicitly June-only Stage 3.6 test.

If any readiness requirement fails, use the documented transparent rule-based fallback and stop searching for another region. Do not weaken thresholds or train a classifier on a failed readiness result. A passing result supports locking this region/window for the two-class demo scope, without implying verified fire causes. Classifier training remains a later task.

## Validation and limitations

Run the complete suite twice and compare full SHA-256 hashes for both new CSV datasets, OSM coverage CSV, readiness report and aggregate manifest. The second run blocks Requests and socket connections, including the real-cache integration tests. Deterministic CSV order is acq_date, acq_time, latitude, longitude, satellite, hotspot_id. Serialized JSON keys are sorted, and no current timestamp enters generated CSVs or reports. Per-query OSM snapshot metadata is immutable input provenance.

OSM is incomplete and may represent infrastructure after the June detections. Power/industrial tags can include non-combustion facilities; unmapped mining and coincident nearby burning remain confounders. Broad landuse polygons and overlapping object records are not independent facilities. Land-cover change, coarse VIIRS geolocation, observation gaps and spatial recurrence limit proxy purity. These are data-readiness checks, not real-world fire-cause validation.

## Completed Stage 3.6 validation

Both complete-suite runs passed **141 tests**. Validation blocked Requests HTTP dispatch and socket connections; zero network attempts occurred. The second pipeline run reused all nine buffered caches, regenerated the four processed outputs, and reproduced their SHA-256 hashes plus the aggregate manifest hash exactly. All per-query manifests and raw responses also remained unchanged. The 2,255 warnings per suite run are upstream Rasterio/Affine pending-deprecation warnings; there were no test failures.

Initial acquisition downloaded nine successful responses because no older unbuffered response covered a required buffered box. Four HTTP 429 responses were preserved; each affected cell succeeded on attempt 2. Total: 13 HTTP responses, nine success and four rate-limit responses, with no cell exceeding three attempts. The second run downloaded zero responses. No additional WorldCover tile was downloaded.

The 674-row June audit contains 308 industrial_candidate, 79 wildfire_candidate, 208 cropland_hotspot_candidate and 79 unknown rows; conflict_excluded and unknown_context_unavailable are both zero. All native FIRMS fields and all 674 persistence counts were independently verified against the normalized input. All rows have complete calendar history and valid required context. Three nominal footprints are edge-clipped and explicitly flagged; their centre pixels remain valid.

The 387 training candidates contain 308 industrial rows (79.5865633075%) and 79 wildfire rows (20.4134366925%), balance ratio 3.8987341772. All nine readiness conditions pass. The expanded half-open 21-24 N / 72-75 E region can be locked for the industrial/wildfire June 2026 demo scope. No classifier was trained, no final predictions were generated, and no further region search was initiated.

| Deterministic output | Run 1 SHA-256 | Run 2 SHA-256 |
| --- | --- | --- |
| expanded_region_june_audit.csv | 592cf0df34b90ecb05511343508c1bd4bccd06fc539e5438a8c41646e8d08f1a | 592cf0df34b90ecb05511343508c1bd4bccd06fc539e5438a8c41646e8d08f1a |
| expanded_region_training_candidates.csv | 84b06234ec7a70edd9852297949d82dbfae0fe48039f15376f9bff741d5f0b1d | 84b06234ec7a70edd9852297949d82dbfae0fe48039f15376f9bff741d5f0b1d |
| expanded_region_osm_coverage.csv | 8470c4603e4cdc0c117691104464150b6e5d3c22677a26f0364ef6f0511d4e83 | 8470c4603e4cdc0c117691104464150b6e5d3c22677a26f0364ef6f0511d4e83 |
| expanded_region_readiness.md | eaf5cc119701a31c193330243793e2b0d57bbab9b7ef8ffdfa3767f5fead9678 | eaf5cc119701a31c193330243793e2b0d57bbab9b7ef8ffdfa3767f5fead9678 |
| data/raw/osm/expanded_region/manifest.json | 4b99f27f30419bf5106a50aa593a2f7ecf2d6f32835b8aab6646b8337c6a69a5 | 4b99f27f30419bf5106a50aa593a2f7ecf2d6f32835b8aab6646b8337c6a69a5 |

The pre-edit file snapshot comparison confirmed that README.md is the only existing file modified (Stage 3.6 execution instructions were appended). The other 63 existing files, including every Stage 1-3.5 source, test, document, raw input and output, retained their exact hashes. The eight requested Stage 3.6 files, nine per-query manifests and 13 raw responses were created. No classified_hotspots.csv or feature_importances.json exists.
