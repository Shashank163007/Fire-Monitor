# Stage 2.5 region selection method

This stage recommends a single replacement demo cell/month; it does not adopt that recommendation or change the locked Stage 2 scope, data contract, prior files, or classifier plan. Only the five requested new code/test/document/report files and explicitly requested raw-response cache under `data/raw/osm/region_scan/` are created. All Stage 1/2 files are read-only. No final fire classes, classifier, frontend, land cover, or VNF are produced.

## Reproduce in Windows VS Code PowerShell

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
.\.venv\Scripts\python.exe -B src\scan_demo_regions.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Existing dependencies are reused. `-B` and disabling the pytest cache prevent modifying prior bytecode and test-cache files. The first scan needs access to the free Overpass endpoint; later runs use saved real responses. The README is deliberately unchanged as instructed. The script hashes protected prior files before/after execution. Tests use isolated temporary fixtures, never production OSM substitutes.

## Fixed candidate screen (before inspecting new OSM results)

Read the full normalized FIRMS dataset for May 1-September 10, 2026 inclusive, **133 calendar days**. Use global floor(latitude), floor(longitude) indices, origin (0, 0). Every candidate is exactly one degree wide/high; south/west included, north/east excluded. No bbox buffer or expansion is allowed. Adjacent boxes share only their edges and never share a detection. Preserve each original hotspot ID in memory; do not create a new production hotspot dataset.

Keep cells with N >= 100 detections and A >= 10 distinct acquisition dates. Among eligible cells define `P_N` and `P_A` as ascending percentile ranks of N and A using average rank for ties (pandas `rank(method="average", pct=True)`). Let B_presence = 1 if both D > 0 and N_night > 0, else 0.

```text
screen_score = (P_N + P_A + B_presence) / 3
```

Sort descending by screen_score, detection count, active dates, then ascending region_id for a deterministic tie-break. Select the first six or fewer. This explicitly combines all three requested screening criteria without letting the very high May detection totals alone choose all candidates. The score is only a shortlist tool. A six-cell shortlist can omit good industrial regions and does not establish a globally optimal choice. The previous mining-heavy cell can qualify and is then rescanned under the same rules as its peers.

## Exactly one combined Overpass query per candidate

Endpoint: `https://overpass-api.de/api/interpreter`, free and without keys/accounts. Each candidate uses one `nwr` union containing the ten requested industrial selectors plus `landuse=quarry` and `man_made=mineshaft`, with its exact bounding box and `out body geom`. There are no separate industrial/mining queries, name searches, or successful-request repeats. Exact queries appear in the selection report. Up to three total attempts (initial request plus two retries) use 2- and 4-second exponential delays; connection/read timeouts are 15/60 seconds and the query timeout is 45 seconds.

Save each received HTTP body unchanged, including error bodies, under `data/raw/osm/region_scan`. Filenames encode region, endpoint/query hash, UTC retrieval time, attempt and HTTP status. Report SHA-256 hashes and request outcomes. Cached HTTP-200 JSON must contain an elements list and no Overpass error remark. Invalid/partial bodies cannot be used. Network failures without a response have no body to cache and are recorded as errors. Exhausted candidates are `unavailable` with null OSM statistics, score and rank; they are never assigned fabricated zero counts. Successful empty results represent zero retrieved context, not a coverage guarantee. No new scan beyond the initial selected six is made to replace unavailable candidates.

## Context and distance consistency

Reuse Stage 2 `convert`, `densify`, and `nearest_asset` as read-only imported functions. Partition the single response by industrial/mining tags in memory; preserve nodes, closed polygons, multipolygons and holes. Explicit mining tags are diverted from industrial context, and industrial geometry intersecting mapped mining geometry is excluded under the same conservative Stage 2 rule. Log unsupported/invalid geometry and overlap exclusions in the selection report. OSM type/ID is the object identity; features are not independent-facility counts.

Use the same WGS84 ellipsoid, point-centered AEQD transformation, geodesic polygon-edge densification to at most 100 m, full-footprint nearest points and final `Geod.inv` distance in km as documented in `docs/feature_engineering.md`. Empty eligible pools yield no proximity matches; no centroid fallback is used. Cache identical coordinate calculations in memory only. Every FIRMS detection contributes once to percentages, even if many detections share one location/day. `near_industrial` and `near_mining` are in-memory proximity flags, not final labels, and no per-hotspot output file is written in this stage.

## Corrected exact suitability normalization

Scoring runs after all candidate query outcomes are known. Let H be the maximum active_dates among successfully queried candidates only (H = 100 in this scan). Clamp each of these five component inputs to [0, 1]:

- A = candidate_active_dates / H; if H is zero, A = 0.
- B = 1.0 when both day and night counts are positive; 0.5 when only one is positive; 0.0 when neither has a valid observation. Counts measure presence, not balance.
- I = pct_near_industrial / 100.
- F = 1.0 when Overpass succeeds and returns usable non-mining industrial features; 0.5 for successful queries with no usable industrial features; 0.0 for a failed query.
- M = pct_near_mining / 100.

```text
active_date_component = 30 * A
day_night_component = 20 * B
industrial_proximity_component = 25 * I
osm_availability_component = 15 * F
positive_subtotal = active_date_component + day_night_component
                  + industrial_proximity_component + osm_availability_component
normalized_positive_score = (positive_subtotal / 90) * 100
mining_penalty = 30 * M
suitability_score = round(max(0, min(100,
                        normalized_positive_score - mining_penalty)), 2)
```

The positive subtotal is normalized before subtracting mining. Maximum positive components produce 100; 100% mining dominance subtracts exactly 30 before clipping. No intermediate values are rounded. These are demo-suitability points, not risk, probability or ML output. Each region's inputs, components and subtotal are recorded in the selection report.

Missing OSM statistics are not imputed. Failed-query rows remain in the CSV with null score/rank; they are excluded from H, ranking and recommendation even if a stale numeric score is supplied. All-failed scans produce an explicit blocker and no recommendation. Successfully empty features mean no retrieved matching context, not evidence that infrastructure is absent. The numerical scoring helper defines failed-query F = 0, but publication with missing proximity inputs is withheld instead of inventing them.

Rank successful candidates using exactly: (1) higher rounded suitability_score, (2) higher pct_near_industrial, (3) lower pct_near_mining, (4) more active_dates, (5) region_id alphabetically. Detection count is not a tie-break. The CSV retains its exact 16 columns; component details live in the report.

## One region and one month

Recommend the highest-ranked available region with a nonempty eligible complete month. Month candidates are June, July, August 2026: all have a complete previous calendar month within the supplied history. May lacks April history; September ends on the 10th. For the separate month comparison, use the corrected formula with A = active_dates / maximum active_dates among that region's nonempty complete-month options, and its successful OSM availability. This local month denominator is reported separately from H; it does not affect region ranking. Before month score, prefer months with >=10 active dates, both day/night, and at least one industrial-proximate detection plus at least one detection outside industrial proximity. Outside proximity means unknown, not natural-fire ground truth. Break remaining month ties by rounded month score descending, industrial percentage descending, mining percentage ascending, active dates descending, then earliest month. Region selection uses the exact region_id tie-break specified above.

If no preferred-evidence month exists, recommend the highest-scoring nonempty complete month with that limitation explicitly stated. If all candidate queries fail, report the blocker without inventing a recommendation. The report provides monthly counts to distinguish a strong full-period score from a weak target-month sample.

Only the month immediately before the target month is retained as prior history. For later persistence, use detections from that history month plus the target month, then each target day's inclusive d-29 through d window. Earlier months used in screening are not target rows or persistence history. No new month/region feature-base file is created or adopted in this stage.

## Limits on a defensible recommendation

Compare against the existing June region's measured 75/736 industrial proximity and 659/736 mining proximity. Lower mapped mining proximity reduces an identified confound; unknown detections remain unverified. Full-period and month comparisons are not controlled causal experiments. OSM snapshot dates can differ between scans and from FIRMS acquisitions. Missing/outdated tags, bbox edge omissions, marker-versus-footprint differences, geometry exclusions, unmapped mines and overlapping facility objects affect percentages. A zero mining result never proves absence of mining. The shared numerical distance approximation and coarse FIRMS geolocation remain limitations. Clouds, incomplete overpass coverage, and seasonal imbalance affect date counts. Spatial/temporal leakage must be addressed before later training. No land-cover or VNF check has been performed.

OSM proximity is **weak-label evidence, not ground truth**. Recommendation does not claim verified industrial/natural class counts or ground-truth accuracy. Raw data attribution: © OpenStreetMap contributors, ODbL; https://www.openstreetmap.org/copyright.

## Corrected-score validation

The correction reuses the same six cells and saved real Overpass responses. It does not modify Stage 1/2 files or adopt a new scope. The complete test suite passed **40 tests in 0.73 seconds** on 2026-09-11. It checks 0-100 bounds, component clamps, a 100-point positive maximum, an exact 30-point maximum mining deduction, presence-based day/night inputs, all availability states, failed-query exclusion from the denominator and recommendation, and every deterministic tie-break priority. The commands above regenerate both comparison outputs with the corrected score.
