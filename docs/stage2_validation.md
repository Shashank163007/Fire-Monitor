# Stage 2 execution results

Completed locally on 2026-09-11. Python 3.14.7 and the Stage 1 environment were reused without installing additional packages.

| Metric | Result |
| --- | --- |
| June target rows | 736 |
| May history rows in demo bbox | 1,288 |
| Persistence min / Q1 / median / Q3 / max | 1 / 11 / 18 / 21 / 28 distinct dates |
| Persistence mean / standard deviation | 16.0231 / 6.8794 |
| Industrial-query retrieved objects | 268 |
| Mining-query retrieved objects | 224 |
| Usable non-mining industrial objects | 209: 187 polygons, 4 multipolygons, 18 points |
| Mining-context objects | 226: 224 quarry-query objects plus 2 industrial=mine objects |
| Industrial objects excluded for mining overlap | 57 |
| Geometry conversion rejections | 0 |
| Named retrieved industrial / mining-query objects | 58 / 22 |
| Industrial candidates | 75 |
| Unknown candidate status | 661 |
| Targets with a nearest mine/quarry distance | 736 |
| Targets within 1 km of mining geometry | 659 |
| Industrial candidates also within 1 km of mining | 23; ambiguous context requiring later review |
| Tests | 16 passed in 0.66 seconds |

Per-tag counts, exact queries, endpoint, raw-response hashes and filenames are in [the coverage report](../outputs/osm_coverage_report.md). Both successful responses describe OSM base timestamp `2026-09-11T09:30:50Z`. This current OSM snapshot is not June ground truth. Overlapping OSM site/building objects are not distinct facilities.

The first sandbox run failed all three industrial-query attempts because its configured proxy refused the connection; it produced a clear blocker report and no feature CSVs. The authorized network retry succeeded on the first attempt for each query (two HTTP 200 responses, no server failures). A subsequent fully cached run required no network and reproduced both feature CSVs byte-for-byte. The final generated coverage report shows those two verified cache hits and retains original successful-fetch metadata. Initial failures were sandbox connection failures, not Overpass rate limits or absence of OSM data.

One test initially found that cached request metadata overwrote the `cache_hit` status with the original `success` status. This was fixed and all tests passed. Tests cover distinct dates, same-day duplicates, both inclusive 30-day boundaries, future exclusion, grid boundaries, geodesic point distances, polygon footprints/holes, split-ring relations, mining exclusions, retries, rate-limit/partial responses, raw-body preservation and cache integrity.

Both feature files have 736 one-to-one matching IDs and June dates only. Distances match between base and audit, candidate status matches the 1 km condition exactly, and all nearest industrial tags pass the non-mining filter. Source `firms_normalized.csv` SHA-256 remained:

```text
fbab81d9f356092ccb7b1593d8b84c6cdf45c4407090ee731b5f77a53004911d
```

Commands executed from `D:\academic_weapon\vscode\SIH26162\fire-monitor`:

```powershell
.\.venv\Scripts\python.exe src\build_features.py
.\.venv\Scripts\python.exe -m pytest -q
```

The feature command was retried with authorized network access after the sandbox failure. Pytest was rerun after the cache-status fix and added mining/rate-limit checks. A read-only validation wrapper invoked the same feature script once more and compared input/output hashes across the cached rerun. No Stage 1 re-profiling, classifier training, final-label output, or frontend build was run.

Later weak labels must account for the very large mining-proximity count, incomplete/current OSM coverage, bbox edge omissions, conservative mine-overlap exclusions, approximate angular grid dimensions, FIRMS observation gaps and geolocation uncertainty. Proximity candidates remain weak evidence, not verified fire causes; unknown is not a negative class.
