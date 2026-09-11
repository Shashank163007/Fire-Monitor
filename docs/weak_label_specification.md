# Stage 3: evaluation-only weak labels

This stage evaluates Candidate A (15 <= latitude < 16, 76 <= longitude < 77) and Candidate B (21 <= latitude < 22, 72 <= longitude < 73), targeting June 1-30, 2026. It recommends a region only if the fixed readiness requirements are met. It does not adopt a new scope, train a classifier, or produce final fire classes. The locked data contract and all Stage 1, Stage 2 and Stage 2.5 outputs remain unchanged. The new CSVs are audit tables, not the final prediction interface.

## Persistence and OSM context

The history pool is May 2-June 30, 2026. For a target date d, persistence is the number of distinct acquisition dates in the same globally anchored 0.01 degree latitude by 0.01 degree longitude cell satisfying d-29 <= date <= d. Multiple detections on one cell/date count once. June 1 uses May 3-June 1, so May 2 is outside every June window. June 30 uses June 1-30. History never contributes extra target rows. This reuses Stage 2's decimal-floor grid and persistence implementation; the grid is approximately 1 km, not a metric square. Counting includes all detections on the target date, even those later than that row's acquisition time; it is a retrospective date-based feature, not a real-time feature.

Distances reuse Stage 2 unchanged: WGS84 ellipsoid, polygon boundaries densified to at most 100 m segments, point-centred ellipsoidal azimuthal equidistant projection for nearest geometry, followed by geodesic distance to that nearest point. Polygon interiors have zero distance. Polygon distance has numerical approximation from densification/projection; point distances use the ellipsoid directly. OSM industrial geometries tagged as mining or intersecting mapped mining are excluded by the existing conversion logic. Both candidates use the exact Stage 2.5 bounding boxes without expansion. Assets beyond query bounds may be missed, especially near edges.

Existing OSM responses are verified against the SHA-256 recorded in the preserved Stage 2.5 report and the endpoint/query hash in the filename. Only missing or invalid caches permit a new free Overpass request; recovery responses go under the new WorldCover raw directory and never overwrite earlier responses. Recovery has three attempts with 2 and 4 second backoff. A failed query produces unavailable context, never invented geometry or distances.

Each context has an explicit status: `available` means usable geometries exist; `no_mapped_objects` means a successful query/conversion returned none; `unavailable` means the query failed. Empty OSM results are not proof that infrastructure or mining is absent. Missing industrial distance is never treated as greater than 1 km. Missing mining distance satisfies the special no-mapped-object exception only after a successful query. Invalid/dropped OSM geometries are recorded in the report's geometry audit.

## Centre pixel and nominal footprint

WorldCover's official 2021 v200 Map supplies a single uint8 band in EPSG:4326 on a 1/12000 degree grid, approximately 10 m. The audit retains the centre-pixel numeric `land_cover_code` and official `land_cover_class`. Code 0, masked pixels and unexpected codes map to `Unknown/Nodata`; the raw numeric code is retained when available. `land_cover_sample_status` distinguishes valid, nodata/unknown and outside-raster samples. Actual candidate coordinates must lie inside their selected raster or the run fails. West/north edges belong to the first pixel; east/south outer edges are outside the raster.

The nominal footprint is a north-up raster window whose limits are the WGS84 geodesic points 195 m north, south, east and west of the hotspot. Raster offsets are rounded outward to include intersecting pixels. It approximates a 390 m by 390 m square, with an additional pixel-rounding margin. It is not a measured sensor footprint or exact fire boundary. Edge windows are masked outside the raster and explicitly flagged as clipped; they are not filled with classes.

`footprint_valid_pixel_count` counts only unmasked official class codes; `footprint_total_pixel_count` includes every pixel in the rounded window, including nodata/outside pixels. Dominant-class proportion and Tree cover, Shrubland, Cropland, Built-up, Bare / sparse vegetation and Water proportions use valid pixels as the denominator. Water means code 80 (Permanent water bodies), not wetlands. Other official classes remain in the denominator, so the six proportions need not sum to one. An empty valid window has unknown dominant class and missing proportions, not zero proportions. Tied dominant counts select the smallest numeric code. The footprint-dominant class never replaces the required centre-pixel class or generates these labels.

FIRMS detections are not exact fire boundaries. VIIRS geolocation and pixel extent vary; the approximately 390 m window is a nominal approximation. WorldCover 2021 is static context for 2026 detections, and land cover may have changed between 2021 and 2026.

## Ordered proxy rules

First guard context availability: either failed OSM context, or a missing distance despite an available geometry set, yields `unknown_context_unavailable`. Otherwise apply the following rules in order. Here I is industrial distance in km; M is mine/quarry distance in km. Mining-clear means M > 1, or M is missing specifically because a successful query returned no usable mapped mining object.

| Priority | weak_label | Conditions |
| --- | --- | --- |
| 1 | conflict_excluded | I <= 1 and M <= 1, regardless of land cover |
| 2 | industrial_candidate | I <= 1, mining-clear, centre class is not Permanent water bodies |
| 3 | agricultural_burn_candidate | Centre is Cropland, I > 1, mining-clear |
| 4 | wildfire_candidate | Centre is Tree cover or Shrubland, I > 1, mining-clear |
| 5 | unknown | Every remaining row |

The 1 km threshold is a conservative proximity heuristic accommodating coarse VIIRS geolocation. It is not verified ground truth. Mining alone never creates an industrial candidate. Under the user's exact rule, Unknown/Nodata is not Permanent water bodies and can therefore receive industrial_candidate when the OSM conditions hold; nodata is separately visible for review. Water excluded from the industrial rule can still be conflict_excluded under the higher-priority conflict rule. No flare label is assigned.

Each row records `weak_label_reason`, `weak_label_source`, and boolean `weak_label_conflict` (true only for conflict_excluded). Unknown is not a negative class. Conflict-excluded, unknown, and context-unavailable rows are excluded from the usable labelled pool. These fields are evaluation-only audit evidence and are not final fire causes.

## Fixed readiness test and recommendation

Usable classes are the three candidate labels. All present usable classes must be counted; a tiny class cannot be discarded to pass the check. A candidate is classifier-ready only if all conditions hold:

1. At least two usable classes are present.
2. Every present usable class has at least 20 rows.
3. No usable class exceeds 85% of usable labelled rows (exactly 85% is allowed).
4. At least 50 usable labelled rows exist.
5. OSM context was successfully available.
6. Conflict-excluded and all unknown categories are excluded from these calculations.

Largest-class percentage is 100 times the largest usable class count divided by total usable rows. Class-balance ratio is largest divided by smallest present usable class count; absent classes are excluded from that denominator, but a single class fails readiness. Empty usable pools have missing percentage and ratio. Each report also includes all centre-pixel class counts and percentages (including zero counts and Unknown/Nodata), day/night and active-date counts, and persistence minimum, median, mean and maximum.

If exactly one candidate qualifies, recommend that one for June 2026. If both qualify, prefer lower largest-class percentage, then more usable rows, then alphabetical region_id. If neither qualifies, make no final-region recommendation. Stage 2.5 suitability is preserved and cannot override these checks. Thresholds are never relaxed automatically, and recommendations do not change the locked current scope.

## Future evaluation and leakage

Industrial distance and land cover generate the weak labels. Using those same fields as classifier inputs creates target leakage: a model can learn the proxy rules rather than independent evidence of fire cause. A train/test score against these labels measures reproduction of proxy rules, not real-world fire-cause accuracy. Later evaluation must report **weak-label agreement**, not **ground-truth accuracy**.

Consider a second ablation model excluding direct label-source features, including industrial/mining distances, land-cover codes/names, proxy-rule indicators and redundant footprint/derived encodings. This can test whether FIRMS-native variables carry independent signal. Spatial and temporal dependence also need attention in a later split design. Neither model is trained in Stage 3.

VNF is a blocked optional future source pending a separate data-use licence/application. No VNF data, adapter schema or fabricated matches are introduced.

## Reproducibility

Original normalized hotspot IDs and zero-padded HHMM acquisition times are preserved. Audits sort by acq_date, acq_time, latitude, longitude, hotspot_id; CSVs use fixed numeric formatting and no generation timestamp. Source snapshots and checksums remain in the manifest/report. Logging timestamps are operational only and do not enter deterministic processed outputs. Valid raw files are reused and checked against their manifest hashes. Official-data failure stops clearly, without dummy replacements.
