# Stage 3 data sources and provenance

## ESA WorldCover

Product: ESA WorldCover 10 m 2021 Map, version v200. [Official data access](https://esa-worldcover.org/en/data-access) and the [v200 Product User Manual](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PUM_V2.0.pdf) document the product and public downloads. Attribution: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Only two original 3 degree by 3 degree COG Map tiles are required. Downloads use unsigned HTTPS from the official public ESA WorldCover AWS bucket, with no AWS CLI, API key, billing account or Google Earth Engine. The v200 manual's download example uses the shared [official 3-degree grid](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/esa_worldcover_2020_grid.geojson), whose path contains v100/2020. That index is used only to select tile IDs; every downloaded Map raster is explicitly 2021 v200. Tile rectangles use index geometry bounds because mapped-land footprints in the index can contain holes; the GeoTIFF covers the whole rectangle.

All files below are stored unchanged under `data/raw/worldcover/v200/`. The index is 5,063,821 bytes, SHA-256 `6d3dc7bea6a4fb8b61dffad358be7c086637549429e7091db2895111a1ad814b`.

| Tile and exact download source | Size in bytes | SHA-256 |
| --- | ---: | --- |
| [ESA_WorldCover_10m_2021_v200_N15E075_Map.tif](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N15E075_Map.tif) | 103154625 | 59e0a7f216b2d75042deb00256bfe48e1683e98b17ecbf978b70d9ab6885f67b |
| [ESA_WorldCover_10m_2021_v200_N21E072_Map.tif](https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N21E072_Map.tif) | 133840887 | 76d26bcf59645b0dc60c824a5a8c4237aa53ac6b880bd22df4c069bd8d91677e |

Both downloads returned HTTP 200 with nonzero complete bodies. Validation confirmed readable GeoTIFFs, EPSG:4326, one uint8 Map band (band 1), 36000 by 36000 pixels, 1/12000 degree spacing, and nodata 0. Bounds (west, south, east, north) are (75,15,78,18) and (72,21,75,24), respectively. These rectangles cover the candidate boxes; every actual hotspot coordinate is additionally checked before sampling. Representative blocks are decoded on acquisition/cache validation and actual windows are decoded during feature generation. A manifest checksum detects subsequent local corruption; it is a locally calculated checksum, not an independently published ESA checksum.

`manifest.json` records product/version, source page, exact URLs, filenames, sizes, SHA-256 values, CRS, bounds, band, resolution, attribution and licence. New downloads use temporary partial files, size checks and raster validation before acquiring their final filenames. Valid cached files are not downloaded again. Failed official acquisition aborts; corrupt caches fail integrity checks rather than being silently replaced. No output-generation timestamps are stored in the manifest or processed outputs.

The official class mapping is 10 Tree cover; 20 Shrubland; 30 Grassland; 40 Cropland; 50 Built-up; 60 Bare / sparse vegetation; 70 Snow and ice; 80 Permanent water bodies; 90 Herbaceous wetland; 95 Mangroves; 100 Moss and lichen. Unknown/nodata is kept separately. See [weak-label specification](weak_label_specification.md) for centre sampling and nominal-footprint handling. This 2021 map is static context for 2026 detections, not a contemporaneous land-cover survey.

## Local FIRMS input

The existing `data/processed/firms_normalized.csv` is used without alteration, SHA-256 `fbab81d9f356092ccb7b1593d8b84c6cdf45c4407090ee731b5f77a53004911d`. It contains the Stage 1 normalized NOAA-20 VIIRS observations from the supplied archive/NRT ZIP. The original source files, metadata and validation remain documented in the preserved Stage 1 reports. June targets retain May detections only for each row's trailing persistence window; original hotspot IDs and FIRMS measurement fields are preserved. Detections and persistence do not establish a verified fire cause.

## OpenStreetMap via free Overpass

Attribution: © OpenStreetMap contributors; [OpenStreetMap copyright and ODbL](https://www.openstreetmap.org/copyright). The exact Stage 2.5 queries, endpoint, request history and raw snapshots remain in `outputs/demo_region_selection.md` and `data/raw/osm/region_scan/`. Stage 3 reuses those successful responses after verifying hashes and query identity. No new Overpass requests were needed for these candidates.

| Candidate | Preserved successful raw filename | SHA-256 |
| --- | --- | --- |
| A | cell_15_76_5f51f6373c559741_20260911T094704521202Z_attempt2_http200.json | 1c2913ac6a0eab21194c1610f1be6f3600379b8c5dd5e50347428daae97e7c93 |
| B | cell_21_72_96a22d6315009390_20260911T094723609829Z_attempt1_http200.json | 35f26bcbb3043b1cd614653ca6f89c8a58feadfcaa82fb13835a2130fe0d17e1 |

Stage 3's decision report repeats query provenance and conversion counts. OSM is incomplete, potentially newer than the detection date, and restricted to the unexpanded candidate boxes. Tagging and valid geometry availability vary; absence of returned features is not proof of absent infrastructure. Industrial features can include renewable power or sites without combustion. Mine geometry exclusion is conservative and may remove mixed sites. The proximity rules are weak-label evidence only, not ground truth.

## Blocked optional future source

VNF requires a separate data-use licence/application and remains a blocked optional future source. No VNF data were downloaded, no adapter schema was created, and no flare labels or matches were fabricated.

## Completed Stage 3 validation

The complete project suite passed: **71 tests**, with 16 upstream Rasterio/Affine pending-deprecation warnings and no failures. The new tests cover official class mapping, nodata, coordinate/pixel and raster boundaries, nominal footprints, ordered weak-label rules and context failure, readiness thresholds, deterministic sorting, cache integrity, bounded download failure, and rejection of incorrect raster CRS/band/resolution.

The feature script completed using only the two official tiles and preserved OSM caches. Two subsequent runs with all Requests HTTP calls forced to fail made zero network requests and produced byte-identical copies of both audit CSVs, the comparison CSV, decision report and manifest. A separate calculation verified each of the 503 persistence counts directly from local FIRMS dates/cells and confirmed that all required native FIRMS fields were preserved. Every target centre pixel is valid. Candidate B has one edge-clipped nominal footprint, with 79.07% valid pixels; Candidate A has none. This is flagged in the audit and does not change centre-pixel labels.

The readiness result is no final-region recommendation: A has 176 industrial, 16 agricultural-burn and 4 wildfire candidates, with 89.80% in its largest usable class. B has 220, 45 and 10 respectively, with 80% in its largest usable class. A fails minimum class size and the 85% limit; B fails minimum class size. No small classes were dropped, thresholds relaxed, or scope changed. No classifier, final predictions, classified_hotspots.csv or feature_importances.json was created.

Only README.md and requirements.txt were modified among pre-existing project files; the latter adds Rasterio. SHA-256 comparison against the pre-edit snapshot confirmed preservation of all previous source, tests, documentation, normalized data, raw OSM files and outputs.
