# Stage 3.5 methodology correction and extended-window evaluation

The evaluated region is 21 <= latitude < 22, 72 <= longitude < 73. Target dates are June 1-September 10, 2026 inclusive: one region, one continuous 102-calendar-day window. The available normalized dataset begins May 1 and ends September 10. May detections contribute only to persistence history. This document supersedes the agricultural-label interpretation for Stage 3.5 without altering historical Stage 3 files or the locked final output field contract.

## Correcting cropland labels

Stage 3 used `agricultural_burn_candidate` for cropland sufficiently far from mapped industry/mining. The locked methodology requires both cropland and defensible regional burning-season evidence. Cropland alone cannot support that agricultural-burning interpretation. No regional burning-season calendar is available in the allowed inputs, and none is invented here.

Stage 3.5 therefore uses `cropland_hotspot_candidate`, which is contextual audit information only. It is never an eligible classifier class and is never assigned final `agburn`. The current classifier scope is limited to industrial and wildfire. Historical Stage 3 rules, reports, CSVs and tests remain preserved as historical records; their agricultural counts must not be carried forward as validated agricultural-burning evidence.

## Exact persistence and calendar completeness

For an acquisition date d:

```text
window_start = d - 29 calendar days
window_end = d
persistence_count_30d = number of DISTINCT acquisition dates t in the same
                       globally anchored 0.01 degree grid cell,
                       where window_start <= t <= window_end
```

Both boundaries are inclusive: exactly 30 calendar dates. June 1 starts May 3; September 10 starts August 12. Multiple detections, including day/night detections, in the same cell/date count once. The current date includes all its available detections, even ones acquired later than the target row's time, so this remains a retrospective daily batch feature. Dates after d do not contribute. Stage 2's distinct-date counting implementation already implements this formula correctly and is reused unchanged.

The shared date-range selector reads only actual normalized observations. The available lower bound is the latest of May 1, the requested history start, and the full normalized dataset's earliest date; the upper bound is the earlier of the target end and the normalized dataset's last date. `persistence_history_complete` is true exactly when [d-29,d] lies inside these available calendar bounds. A May 29 example is incomplete (starts April 30); May 30 is complete (starts May 1). No pre-May observations are invented.

This flag describes calendar-range availability, not complete satellite observation coverage. FIRMS is a detection table, not a daily observation-status log: a date with no detection does not prove missing input or zero fire. We do not require a detection on every one of the 30 dates. Clouds, orbital coverage, missing observations, cell boundaries and geolocation jitter still affect observed recurrence. Grid cells are degree-based, approximately 1 km, not constant metric squares. Incomplete-history rows stay in the audit and are excluded from future training by default; any exception requires explicit justification.

## Reuse and offline behavior

`src/build_landcover_features.py --extended` uses the shared `select_feature_targets` and `build_feature_audit` functions. The Stage 3 wrapper retains its original June defaults and legacy label names; Stage 3.5 adds only its date range, history flags, corrected label interpretation and readiness evaluation. It does not copy a separate raster/OSM feature pipeline.

The original normalized FIRMS file, official grid, WorldCover manifest and N21E072 2021 v200 Map tile are read-only. The tile is verified against its cached checksum/size, official grid bounds, CRS, dimensions and band. A missing/invalid WorldCover cache fails clearly and does not trigger a download or rewrite the manifest. WorldCover attribution/licence and exact URLs/checksums remain documented in [Stage 3 data sources](data_sources.md) and are repeated in the extended decision's provenance.

The existing Stage 2.5 OSM response is checked by SHA-256 and endpoint/query identity, then its industrial and mining geometries are reconstructed with Stage 2's conversion, mining exclusions and distance functions. `allow_network=False` prevents recovery requests. Missing/invalid OSM cache or failed geometry reconstruction becomes `unknown_context_unavailable`, not a fabricated distance or an absence claim. All responses and older outputs remain unchanged. Tests prohibit both Requests HTTP calls and socket connections during Stage 3.5 execution.

Distance is the existing WGS84 ellipsoidal nearest-geometry method: densified polygon edges, hotspot-centred AEQD nearest point, then geodesic distance in km; polygon interiors have zero distance. The 1 km threshold remains a conservative VIIRS proximity heuristic. It is not cause verification. Geometry or tagged-object counts do not equal distinct facility counts.

## Ordered Stage 3.5 labels

Let I be distance to non-mining industrial geometry and M distance to mine/quarry geometry. Mining-clear means M > 1 km, or missing M specifically because successfully reconstructed query context contains no mapped mining objects. Never infer this from a failed query. Inconsistent status/distance pairs, negative/nonfinite distances and failed reconstruction make context unavailable.

| Priority | Label | Requirements |
| --- | --- | --- |
| 1 | conflict_excluded | Valid OSM context; I <= 1 and M <= 1, regardless of land cover |
| 2 | industrial_candidate | Valid OSM context; I <= 1, mining-clear, centre class is not Permanent water bodies |
| 3 | wildfire_candidate | Valid OSM context; centre Tree cover or Shrubland, I > 1, mining-clear |
| 4 | cropland_hotspot_candidate | Valid OSM context; centre Cropland, I > 1, mining-clear; audit only |
| 5 | unknown_context_unavailable | Required OSM context failed, is inconsistent, or could not be reconstructed |
| 6 | unknown | Every remaining row |

Context validity is a prerequisite for rules 1-4; evaluating the failure guard before those predicates implements priority 5 without allowing stale distances to override failed context. Tree/Shrubland and Cropland are disjoint centre classes, so reusing the original spatial predicates and renaming the cropland result preserves the requested priority. Each row records reason, source and conflict status. No flare or final class is assigned.

The centre pixel remains `land_cover_class` and retains its numeric code. All nominal-footprint fields are reused unchanged and remain audit-only. Unknown/nodata may satisfy the literal industrial non-water predicate, but cannot enter the valid-context eligible pool. A clipped nominal footprint is flagged; it does not invalidate an otherwise valid centre pixel. Missing industrial distance from an empty successful query is never interpreted as greater than 1 km. Missing mapped objects are not proof of real-world absence.

## Eligibility, readiness denominators and reporting

The audit explicitly distinguishes:

- `training_context_complete`: valid OSM status/distance pairs and an official numeric centre code matching its valid class name.
- `label_context_eligible`: industrial_candidate or wildfire_candidate with complete OSM/land-cover context, before history filtering.
- `training_eligible`: label_context_eligible and persistence_history_complete. Only these rows may enter later training by default.

Readiness class counts, balance and month concentration use the label_context_eligible pool. The history completeness percentage uses that pool before incomplete-history rows are filtered, preserving a meaningful 80% check. Monthly `eligible_training_rows` and reported training class counts use the stricter training_eligible mask. Both denominators are reported explicitly. All actual target rows in this evaluation have complete history, so these two eligible counts coincide.

The seven fixed conditions are:

1. At least 20 industrial candidates with complete OSM/land-cover context.
2. At least 20 wildfire candidates with complete OSM/land-cover context.
3. At least 50 total eligible-context rows.
4. Largest eligible class / total eligible rows <= 90%.
5. Every eligible row has valid OSM and land-cover context; an empty eligible pool fails.
6. Complete-history eligible rows / all eligible-context rows >= 80%.
7. For each class separately, its largest calendar-month count / its total eligible-context class count <= 80%. A missing class fails this test.

Exact limits are inclusive. No thresholds are relaxed, no minority class is dropped and no cropland rows are reclassified to improve balance. Monthly reporting separates June, July, August and September 1-10, including zero categories. September remains a partial month and is not extrapolated. Eligibility does not establish model readiness: a row can be eligible while the aggregate region still fails readiness.

The decision is **cannot lock this region/window**. There are 443 target hotspots, 365 industrial candidates and 11 wildfire candidates. Industrial rows comprise 97.07% of the two-class eligible pool; 10 of 11 wildfire candidates (90.91%) occur in June. Conditions 2, 4 and 7 fail. Conditions 1, 3, 5 and 6 pass. The two-class methodology correction is retained, but it does not authorize training on this failed region/window. See [monthly counts](../outputs/extended_window_label_distribution.csv) and the [complete decision](../outputs/extended_window_decision.md).

## Limitations and validation protocol

OSM proximity and centre land cover are proxy evidence, not verified fire causes. Industrial proximity can coincide with unrelated burning; mapped forest/shrubland does not establish wildfire cause. OSM is incomplete, bbox-limited and not necessarily contemporary with 2026 observations; unmapped mining remains possible. ESA WorldCover 2021 is static context for 2026, and land cover may have changed. FIRMS detections are not exact boundaries, and the nominal 390 m square is only an approximation. No new external data, regional burning-season calendar or VNF matches were introduced. VNF remains an optional blocked source requiring a separate licence/application.

Industrial/mining distance and land cover generate labels; using those fields or close derivatives as inputs creates target leakage. Later evaluation must report weak-label agreement, not ground-truth accuracy. Consider a separate ablation excluding direct label-source features, along with spatial/temporal validation. Neither classifier is trained here.

Run the extended pipeline and complete project suite twice, with networking disabled for validation. Compare SHA-256 for the extended audit, monthly CSV and decision report between runs. The two CSV hashes are also embedded in the decision report; calculate its own full-file hash externally to avoid a self-referential hash. Stable sorting uses acq_date, acq_time, latitude, longitude, hotspot_id, preserving zero-padded acquisition times and original IDs. Processed outputs contain no changing timestamp. Tests also verify June features remain equal to preserved Stage 3 values, with only the intended cropland-label correction in Stage 3.5.

## Completed validation

Both validation runs regenerated all three artifacts and ran the complete project suite: **109 tests passed in run 1 and 109 passed in run 2**, with zero network attempts in both. Requests HTTP dispatch and socket connections were blocked during generation and tests. The suite emitted 904 upstream Rasterio/Affine pending-deprecation warnings per run, with no failures. The second run's three full-file hashes exactly matched the first.

| Output filename | Run 1 SHA-256 | Run 2 SHA-256 |
| --- | --- | --- |
| region_21_22_72_73_extended_audit.csv | ace90e94668efbb578e49e8b8ee629305e319098e19d3d8a1bf2b73ffc370b63 | ace90e94668efbb578e49e8b8ee629305e319098e19d3d8a1bf2b73ffc370b63 |
| extended_window_label_distribution.csv | d4391b1bb693712da324b8f979f7f022056233b84828beac60f27d276abe2a2f | d4391b1bb693712da324b8f979f7f022056233b84828beac60f27d276abe2a2f |
| extended_window_decision.md | 1c1401a12c5af90a949eaca3cfd2cf1049a298979176047f26c1c596a8746e66 | 1c1401a12c5af90a949eaca3cfd2cf1049a298979176047f26c1c596a8746e66 |

A separate calculation checked all 443 persistence counts directly against distinct normalized acquisition dates in each cell and confirmed preservation of native FIRMS fields. All 443 rows have complete calendar history and valid OSM/centre land-cover context. Eligible training rows are 365 industrial and 11 wildfire; 49 cropland-context rows and 18 unknown rows remain excluded. Conflict-excluded and context-unavailable counts are zero in every reporting period.

The pre-edit SHA-256 snapshot comparison confirmed that only `src/build_landcover_features.py` and `README.md` changed among existing project files. The other 57 snapshotted files, including all Stage 1-3 outputs and all raw inputs, remained identical. Exactly the five requested new files were created. No classifier, final predictions, classified_hotspots.csv, feature_importances.json, new external data or agricultural-burning labels were created.
