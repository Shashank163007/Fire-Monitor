# Stage 2 feature engineering

The locked classification interface is unchanged. Stage 2 writes an intermediate feature base and a separate audit; neither is `classified_hotspots.csv`. It creates no final labels, classifier, land-cover features, risk scores, or frontend. Stage 1 inputs are read-only and SHA-256 checked before and after execution.

## Selection and identity

Use 23 <= latitude < 24 and 86 <= longitude < 87 (the same half-open bbox used in Stage 1 screening). June 1-30, 2026 UTC supplies target rows only. May 1-June 30 supplies history; July and later cannot enter any feature. Existing deterministic Stage 1 `hotspot_id` values are preserved, never recomputed or renumbered. Acquisition times stay four-character strings.

The base has exactly `hotspot_id, latitude, longitude, acq_date, acq_time, frp, brightness, confidence, day_night, distance_to_industrial_km, persistence_count_30d`. The audit joins one-to-one on `hotspot_id` and holds grid and nearest-asset context. Other Stage 1 sensor/provenance fields remain recoverable through that ID.

## Persistence

Grid indices are floor(latitude * 100), floor(longitude * 100), using decimal arithmetic to avoid binary rounding at exact cell boundaries. The grid is fixed globally at origin (0 degrees, 0 degrees); each cell includes its south/west edges and excludes its north/east edges. Audit IDs are `g001_<latitude index>_<longitude index>`.

Cells are 0.01 degrees by 0.01 degrees. Near 23.5 N this is approximately 1.11 km north-south by 1.02 km east-west, not a constant metric square and not a precise 1 km pixel.

For cell c and UTC acquisition date d:

```text
persistence_count_30d(c,d) = size of {t : d-29 days <= t <= d,
                                     at least one FIRMS detection in c on date t}
```

Count distinct dates, not detections, overpasses, or FRP. June 1 includes May 3-June 1; June 30 includes June 1-June 30. The current date counts once even when many day/night detections occur. This retrospective daily feature includes all detections on the target date, including those acquired later that day; it is not an acquisition-time live feature. Every observed target has count 1-30. May supplies sufficient calendar lookback for every June target, but clouds, missing observations, and sensor coverage can suppress observed persistence. A date without a detection is not confirmed absence of fire. Geolocation jitter and cell boundaries can split one source across cells.

## Real Overpass context

Only `https://overpass-api.de/api/interpreter` is used, with no key or account. Separate `nwr` unions query all requested industrial tags and quarry/mineshaft tags in the exact demo bbox, using `out body geom`. Names and full tags are preserved on retrieved facilities; name-only matching is avoided because a name does not establish industrial use. Exact queries and per-tag object counts are in `outputs/osm_coverage_report.md`. Overpass syntax follows the [official OSM reference](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL).

Every received response body, including error responses, is saved unchanged as bytes in `data/raw/osm/` before parsing. Timestamped filenames avoid overwriting earlier snapshots. Successful query/endpoint-specific manifests retain endpoint, UTC fetch time, status, and body hash. Default reruns verify and reuse these real caches; `--refresh-osm` obtains a new snapshot. No synthetic fallback exists. At most three attempts per query use 2- and 4-second exponential delays, a 15-second connection timeout, and 60-second read timeout. HTTP errors, network errors, invalid JSON, and Overpass error remarks are logged; incomplete responses cannot be accepted. Exhaustion fails with a nonzero exit and a coverage report explaining the blocker. Any files from a previous successful run must not be treated as results of a failed refresh.

Nodes become points. Closed area ways become polygons. Multipolygon/boundary relations assemble outer and inner member ways, including split rings; holes are subtracted. Invalid, incomplete, open linear, and unsupported nested relation geometries are excluded and listed, never converted to invented centroid footprints. Objects deduplicate by OSM type/ID; overlapping site/building objects remain separate, so counts are not facility counts.

Explicit quarry/mineshaft and industrial mine/mining/quarry/coal_mine tags enter only the mining pool. Non-mining industrial objects intersecting mapped mining geometries are conservatively excluded from the industrial pool and listed in the report. This may also exclude a real industrial plant co-located with a mine. Mining geometry remains available only for separate audit distance. Unmapped or incorrectly tagged mining activity cannot be ruled out.

## Distances and proximity preparation

Coordinates use WGS84 longitude/latitude with explicit longitude-first axis order. Distances use the WGS84 ellipsoid through `pyproj.Geod` and a separate ellipsoidal azimuthal-equidistant (AEQD) projection centered on each hotspot. AEQD radial distances from that origin are geodesic distances. Polygon geodesic edges are densified to at most 100 m before projection, then the nearest point on each full footprint is located; holes are respected and an interior/boundary hotspot has distance zero. All retrieved eligible features are compared. The selected nearest point is transformed back to WGS84 and the final geodesic distance is evaluated with `Geod.inv`, in km. No centroid distance or degree-distance conversion is used.

Polygon nearest-point location is a numerical approximation from densified geodesic edges; it is not an exact analytic ellipsoidal polygon minimum. The tests check point distances against known geodesic displacements, a polygon boundary at a 1 km offset, interior zero distance, and holes. Point/edge mapping and FIRMS geolocation uncertainty are much larger practical limitations than numerical precision. `pyproj` is already installed through GeoPandas; no new service or dependency installation is needed. See [pyproj geodesic documentation](https://pyproj4.github.io/pyproj/stable/api/geod.html).

Only `distance_to_industrial_km <= 1.0` yields audit `industrial_candidate=true`. Otherwise the audit value is `unknown`, not false or a negative class. The 1 km threshold is a conservative proximity heuristic motivated by coarse VIIRS active-fire geolocation. It does not confirm causation, combustion type, or ground-truth industrial fire status. Nearest mine/quarry distance never feeds this condition. No industrial/flare/wildfire/agburn predictions are assigned.

The audit records nearest asset ID, name (null if unnamed), type tags, full tags as JSON, distance, nearest mining ID/distance, and candidate status. No-mining-feature distance is null, never zero. The report distinguishes count of targets with any mining context from count within 1 km of mining geometry; neither is a label.

## Limitations for later weak labels

OSM is a current snapshot, not necessarily the facility state in June 2026. Bbox-limited retrieval misses nearby features outside the box and may miss enclosing polygons without a vertex inside. Missing tagging, excluded geometry, unnamed facilities, overlap exclusions, and broad industrial landuse polygons all affect coverage. Points describe markers, not facility boundaries. Industrial proximity can coincide with unrelated burning. No VNF or land cover has been joined; a flare tag is context only. Later training must treat these as weak/proxy evidence and avoid ground-truth accuracy claims and spatial/temporal leakage.

OSM attribution: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL.
