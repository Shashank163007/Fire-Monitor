"""Stage 3: official WorldCover context and evaluation-only proxy-label readiness."""
from __future__ import annotations

import hashlib
import argparse
import json
import logging
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window, from_bounds
import requests
from shapely.geometry import box, shape
from shapely.errors import GEOSException

if __package__:
    from .build_features import BASE, GEOD, INDUSTRIAL, MINING, convert, densify, grid_id, matches, nearest_asset, persistence, valid_payload
    from .scan_demo_regions import fetch_cell, query_for, ENDPOINT
else:
    from build_features import BASE, GEOD, INDUSTRIAL, MINING, convert, densify, grid_id, matches, nearest_asset, persistence, valid_payload
    from scan_demo_regions import fetch_cell, query_for, ENDPOINT

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/worldcover/v200"
SOURCE = "https://esa-worldcover.org/en/data-access"
BUCKET = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"
# The v200 PUM explicitly uses this official shared 3-degree index for v200 downloads.
GRID_URL = BUCKET + "/v100/2020/esa_worldcover_2020_grid.geojson"
ATTRIBUTION = "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium"
CLASSES = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice", 80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"}
UNKNOWN = "Unknown/Nodata"
USABLE = ["industrial_candidate", "agricultural_burn_candidate", "wildfire_candidate"]
LABELS = USABLE + ["conflict_excluded", "unknown", "unknown_context_unavailable"]
REGIONS = [SimpleNamespace(region_id="region_15_16_76_77", scan_id="cell_15_76", min_lat=15, max_lat=16, min_lon=76, max_lon=77), SimpleNamespace(region_id="region_21_22_72_73", scan_id="cell_21_72", min_lat=21, max_lat=22, min_lon=72, max_lon=73)]
SORT = ["acq_date", "acq_time", "latitude", "longitude", "hotspot_id"]
LOG = logging.getLogger("landcover")
EXTENDED_START, EXTENDED_END = "2026-06-01", "2026-09-10"
AVAILABLE_START = "2026-05-01"
TWO_CLASS = ["industrial_candidate", "wildfire_candidate"]
EXTENDED_LABELS = TWO_CLASS + ["cropland_hotspot_candidate", "conflict_excluded", "unknown", "unknown_context_unavailable"]


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def download(url, path, validator, expected=None):
    """Validate cached bytes; new bytes reach their final filename only after validation."""
    path = Path(path)
    if path.exists():
        metadata = validator(path)
        if expected and (checksum(path) != expected["sha256"] or path.stat().st_size != expected["file_size"]):
            raise RuntimeError(f"Cache integrity mismatch: {path}; not silently replaced")
        LOG.info("Validated cache: %s", path.name)
        return metadata
    partial = path.with_suffix(path.suffix + ".part")
    for attempt in range(1, 4):
        try:
            LOG.info("Downloading official data: %s (attempt %d/3)", url, attempt)
            with requests.get(url, stream=True, timeout=(15, 60), headers={"Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    response.raise_for_status()
                    raise RuntimeError(f"Expected HTTP 200, got {response.status_code}")
                expected_size = int(response.headers.get("Content-Length", 0))
                with partial.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
                size = partial.stat().st_size
                if not size or (expected_size and size != expected_size):
                    raise RuntimeError(f"Incomplete response: {size}/{expected_size} bytes")
            metadata = validator(partial)
            partial.replace(path)
            return metadata
        except (requests.RequestException, ValueError, RuntimeError, rasterio.errors.RasterioError) as exc:
            LOG.warning("Official data download/validation failed: %s", exc)
            if attempt == 3:
                raise RuntimeError(f"Official WorldCover unavailable or invalid: {url}. No dummy replacement.") from exc
            time.sleep(2 ** attempt)


def validate_grid(path):
    data = json.loads(Path(path).read_bytes())
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError("Invalid official tile index")
    return data


def required_tiles(grid, regions=REGIONS):
    selected = {}
    for region in regions:
        bbox = box(region.min_lon, region.min_lat, region.max_lon, region.max_lat)
        # Index footprints can contain holes; the Map GeoTIFF covers its rectangle.
        tiles = [f for f in grid["features"] if box(*shape(f["geometry"]).bounds).intersection(bbox).area > 0]
        if len(tiles) != 1 or not box(*shape(tiles[0]["geometry"]).bounds).covers(bbox):
            raise RuntimeError(f"Expected one fully covering official tile for {region.region_id}")
        tile = tiles[0]
        bounds = list(shape(tile["geometry"]).bounds)
        if bounds[2] - bounds[0] != 3 or bounds[3] - bounds[1] != 3:
            raise ValueError("Unexpected tile-grid dimensions")
        tile_id = tile["properties"]["ll_tile"]
        selected.setdefault(tile_id, {"bounds": bounds, "regions": []})["regions"].append(region.region_id)
    return dict(sorted(selected.items()))


def validate_tile(path, bounds):
    if not Path(path).stat().st_size:
        raise ValueError("Empty GeoTIFF")
    with rasterio.open(path) as src:
        if src.driver != "GTiff" or src.crs != rasterio.crs.CRS.from_epsg(4326):
            raise ValueError("Expected a WGS84 EPSG:4326 GeoTIFF")
        if src.count != 1 or src.dtypes != ("uint8",) or src.indexes != (1,):
            raise ValueError("Expected single uint8 Map band 1")
        if src.width != 36000 or src.height != 36000 or not np.allclose(src.res, [1/12000, 1/12000], rtol=0, atol=1e-12):
            raise ValueError("Unexpected WorldCover Map resolution/dimensions")
        if not np.allclose(src.bounds, bounds, atol=1e-8, rtol=0):
            raise ValueError("Raster bounds disagree with official grid")
        if src.transform.b or src.transform.d or src.transform.a <= 0 or src.transform.e >= 0:
            raise ValueError("Unexpected raster orientation")
        # Decode representative blocks before accepting the file; actual target reads follow.
        for row, col in [(0, 0), (18000, 18000), (35999, 35999)]:
            src.read(1, window=Window(col, row, 1, 1))
        return {"crs": str(src.crs), "raster_bounds": list(src.bounds), "raster_band": 1, "dtype": src.dtypes[0], "width": src.width, "height": src.height, "pixel_size_degrees": list(src.res), "nodata": src.nodata}


def acquire_worldcover():
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    index = RAW / "esa_worldcover_2020_grid.geojson"
    grid = download(GRID_URL, index, validate_grid, old.get("grid"))
    tiles = required_tiles(grid)
    manifest = {"product_name": "ESA WorldCover 10 m 2021 Map", "version": "v200", "official_source_page": SOURCE, "attribution": ATTRIBUTION, "licence": "CC BY 4.0", "licence_url": "https://creativecommons.org/licenses/by/4.0/", "grid": {"exact_download_url": GRID_URL, "local_filename": index.name, "file_size": index.stat().st_size, "sha256": checksum(index)}, "tiles": []}
    for tile_id, info in tiles.items():
        filename = f"ESA_WorldCover_10m_2021_v200_{tile_id}_Map.tif"
        url = f"{BUCKET}/v200/2021/map/{filename}"
        expected = next((t for t in old.get("tiles", []) if t["local_filename"] == filename), None)
        path = RAW / filename
        metadata = download(url, path, lambda p: validate_tile(p, info["bounds"]), expected)
        manifest["tiles"].append({"tile_id": tile_id, "product_name": manifest["product_name"], "version": "v200", "official_source_page": SOURCE, "exact_download_url": url, "local_filename": filename, "file_size": path.stat().st_size, "sha256": checksum(path), "download_http_status": 200, **metadata, "candidate_regions": info["regions"], "attribution": ATTRIBUTION, "licence": "CC BY 4.0"})
        write_json(manifest_path, manifest)
    return manifest


def class_name(code):
    return CLASSES.get(code, UNKNOWN)


def footprint_summary(values):
    data = np.ma.asarray(values)
    valid = data.compressed()
    valid = valid[np.isin(valid, list(CLASSES))]
    count = len(valid)
    result = {"footprint_valid_pixel_count": count, "footprint_total_pixel_count": int(data.size)}
    if count:
        codes, counts = np.unique(valid, return_counts=True)
        dominant = int(codes[np.argmax(counts)])  # deterministic smallest-code tie
        result.update(footprint_dominant_class=class_name(dominant), footprint_dominant_proportion=float(counts.max() / count))
    else:
        result.update(footprint_dominant_class=UNKNOWN, footprint_dominant_proportion=None)
    for code, label in [(10, "tree_cover"), (20, "shrubland"), (40, "cropland"), (50, "built_up"), (60, "bare_sparse_vegetation"), (80, "water")]:
        result[f"footprint_{label}_proportion"] = float((valid == code).sum() / count) if count else None
    return result


def sample_landcover(src, lon, lat):
    row, col = src.index(lon, lat)
    inside = (src.bounds.left <= lon < src.bounds.right and src.bounds.bottom < lat <= src.bounds.top and 0 <= row < src.height and 0 <= col < src.width)
    code = None
    status = "outside_raster"
    if inside:
        pixel = src.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
        code = int(src.nodata) if np.ma.is_masked(pixel) and src.nodata is not None else None if np.ma.is_masked(pixel) else int(pixel)
        status = "valid" if code in CLASSES else "nodata_or_unknown"
    west = GEOD.fwd(lon, lat, 270, 195)[0]
    east = GEOD.fwd(lon, lat, 90, 195)[0]
    south = GEOD.fwd(lon, lat, 180, 195)[1]
    north = GEOD.fwd(lon, lat, 0, 195)[1]
    window = from_bounds(west, south, east, north, src.transform)
    col0, row0 = int(np.floor(window.col_off)), int(np.floor(window.row_off))
    col1, row1 = int(np.ceil(window.col_off + window.width)), int(np.ceil(window.row_off + window.height))
    values = src.read(1, window=Window(col0, row0, col1-col0, row1-row0), boundless=True, masked=True)
    return {"land_cover_code": code, "land_cover_class": class_name(code), "land_cover_sample_status": status, **footprint_summary(values), "footprint_clipped_at_raster_edge": col0 < 0 or row0 < 0 or col1 > src.width or row1 > src.height}


def weak_label(row):
    i, m = row["distance_to_industrial_km"], row["nearest_mine_or_quarry_distance_km"]
    istatus, mstatus = row["industrial_context_status"], row["mining_context_status"]
    unavailable = istatus == "unavailable" or mstatus == "unavailable" or (istatus == "available" and pd.isna(i)) or (mstatus == "available" and pd.isna(m))
    def result(label, reason, source, conflict=False):
        return {"weak_label": label, "weak_label_reason": reason, "weak_label_conflict": conflict, "weak_label_source": source}
    if unavailable:
        return result("unknown_context_unavailable", "OSM context failed or an expected distance is missing", "OSM context status")
    near_i, near_m = pd.notna(i) and i <= 1, pd.notna(m) and m <= 1
    mine_clear = (pd.notna(m) and m > 1) or (pd.isna(m) and mstatus == "no_mapped_objects")
    land = row["land_cover_class"]
    if near_i and near_m:
        return result("conflict_excluded", "Industrial and mining proximity both <=1 km", "OSM industrial + mining geometry", True)
    if near_i and mine_clear and land != "Permanent water bodies":
        return result("industrial_candidate", "Industrial <=1 km; mining clear under mapped-context rule; centre is not water", "OSM proximity + ESA WorldCover 2021 v200 centre pixel")
    far_i = pd.notna(i) and i > 1
    if land == "Cropland" and far_i and mine_clear:
        return result("agricultural_burn_candidate", "Centre Cropland; industrial >1 km; mining clear under mapped-context rule", "ESA WorldCover 2021 v200 centre pixel + OSM proximity")
    if land in {"Tree cover", "Shrubland"} and far_i and mine_clear:
        return result("wildfire_candidate", "Centre Tree cover/Shrubland; industrial >1 km; mining clear under mapped-context rule", "ESA WorldCover 2021 v200 centre pixel + OSM proximity")
    return result("unknown", "No ordered proxy rule satisfied; unknown is not a negative label", "OSM + ESA WorldCover rule evaluation")


def readiness(labels, osm_available):
    counts = pd.Series(labels, dtype="string").value_counts().reindex(USABLE, fill_value=0)
    positive = counts[counts > 0]
    total, classes = int(positive.sum()), len(positive)
    largest = float(positive.max() / total * 100) if total else None
    ratio = float(positive.max() / positive.min()) if classes else None
    failures = []
    if classes < 2: failures.append("fewer than two usable classes")
    if classes and positive.min() < 20: failures.append("a present usable class has fewer than 20 rows")
    if largest is not None and largest > 85: failures.append("largest usable class exceeds 85%")
    if total < 50: failures.append("fewer than 50 usable labelled rows")
    if not osm_available: failures.append("OSM context unavailable")
    return {"usable_labelled_rows": total, "usable_class_count": classes, "largest_class_percentage": largest, "class_balance_ratio": ratio, "classifier_ready": not failures, "readiness_failures": "; ".join(failures)}


def sorted_audit(frame):
    return frame.sort_values(SORT, kind="stable").reset_index(drop=True)


def csv_text(frame):
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.12g", na_rep="")


def osm_context(region, allow_network=True):
    # Verify Stage 2.5 cache bytes against its preserved report before using them.
    query = query_for(region)
    prefix = region.scan_id + "_" + hashlib.sha256((ENDPOINT + query).encode()).hexdigest()[:16]
    try:
        previous = (ROOT / "outputs/demo_region_selection.md").read_text(encoding="utf-8")
        section = previous.split(f"### {region.scan_id}\n", 1)[1]
        prior = json.loads(section.split("```json\n", 1)[1].split("\n```", 1)[0])
    except (OSError, IndexError, ValueError) as exc:
        LOG.warning("Stage 2.5 cache provenance unavailable: %s", exc)
        prior = {"requests": []}
    for record in prior["requests"]:
        if "file" in record and record["file"].startswith(prefix) and record["file"].endswith("_http200.json"):
            path = ROOT / "data/raw/osm/region_scan" / record["file"]
            if path.exists() and checksum(path) == record["sha256"]:
                try:
                    payload = valid_payload(path.read_bytes())
                except (ValueError, TypeError) as exc:
                    LOG.warning("Invalid cached Overpass response: %s", exc)
                    continue
                return payload, {"file": record["file"], "sha256": record["sha256"], "endpoint": ENDPOINT, "query": query}
    if not allow_network:
        return None, {"status": "unavailable", "reason": "No valid matching cached OSM response; Stage 3.5 forbids network requests", "endpoint": ENDPOINT, "query": query}
    # Missing/invalid original cache may be refetched, but never overwrite old raw data.
    fallback = RAW / "osm_recovery"
    fallback.mkdir(exist_ok=True)
    candidate = SimpleNamespace(**{**vars(region), "region_id": region.scan_id})
    detail = {}
    payload = fetch_cell(candidate, fallback, detail)
    return payload, detail


def persistence_window(acq_date):
    end = pd.Timestamp(acq_date).normalize()
    return end - pd.Timedelta(days=29), end


def history_complete(acq_date, available_start, available_end):
    start, end = persistence_window(acq_date)
    return bool(start >= pd.Timestamp(available_start) and end <= pd.Timestamp(available_end))


def select_feature_targets(region, firms, target_start, target_end, history_start, include_history_flag=False):
    if pd.Timestamp(target_start) > pd.Timestamp(target_end) or pd.Timestamp(history_start) > pd.Timestamp(target_start):
        raise ValueError("Invalid target/history date range")
    history = firms.loc[firms.latitude.between(region.min_lat, region.max_lat, inclusive="left") & firms.longitude.between(region.min_lon, region.max_lon, inclusive="left") & firms.acq_date.between(history_start, target_end), BASE].copy()
    history["grid_cell_id"] = [grid_id(a, b) for a, b in zip(history.latitude, history.longitude)]
    target = sorted_audit(history.loc[history.acq_date.between(target_start, target_end)].copy())
    target["persistence_count_30d"] = persistence(history, target)
    if include_history_flag:
        available_start = max(AVAILABLE_START, history_start, firms.acq_date.min())
        available_end = min(target_end, firms.acq_date.max())
        target["persistence_history_complete"] = [history_complete(d, available_start, available_end) for d in target.acq_date]
    return target


def build_feature_audit(region, firms, tile, target_start="2026-06-01", target_end="2026-06-30", history_start="2026-05-02", extended=False):
    target = select_feature_targets(region, firms, target_start, target_end, history_start, include_history_flag=extended)
    if target.empty:
        raise ValueError("No target hotspots in selected region/date range")
    payload, provenance = osm_context(region, allow_network=not extended)
    state = {}
    if payload is not None:
        try:
            ip = {"elements": [e for e in payload["elements"] if matches(e.get("tags", {}), INDUSTRIAL)]}
            mp = {"elements": [e for e in payload["elements"] if matches(e.get("tags", {}), MINING)]}
            industrial, mining = convert({"industrial": ip, "mining": mp}, state)
            di = np.array([densify(g) for g in industrial.geometry], dtype=object)
            dm = np.array([densify(g) for g in mining.geometry], dtype=object)
            istatus = "available" if len(industrial) else "no_mapped_objects"
            mstatus = "available" if len(mining) else "no_mapped_objects"
            if extended and state.get("rejected_geometries"):
                # Empty after geometry rejection is not confirmed absence of mapped objects.
                if ip["elements"] and industrial.empty: istatus = "unavailable"
                if mp["elements"] and mining.empty: mstatus = "unavailable"
        except (ValueError, KeyError, TypeError, GEOSException) as exc:
            if not extended: raise
            LOG.error("Cached OSM geometry reconstruction unavailable: %s", exc)
            state["reconstruction_error"] = str(exc)
            payload = None
    if payload is None:
        istatus = mstatus = "unavailable"
    additions = []
    with rasterio.open(RAW / tile["local_filename"]) as src:
        for n, row in enumerate(target.itertuples(), 1):
            if not (src.bounds.left <= row.longitude < src.bounds.right and src.bounds.bottom < row.latitude <= src.bounds.top):
                raise ValueError(f"Candidate coordinate outside raster: {row.hotspot_id}")
            distance_i = distance_m = np.nan
            if payload is not None:
                distance_i = nearest_asset(row.longitude, row.latitude, industrial, di)[1]
                distance_m = nearest_asset(row.longitude, row.latitude, mining, dm)[1]
            additions.append({"distance_to_industrial_km": distance_i, "nearest_mine_or_quarry_distance_km": distance_m, "industrial_context_status": istatus, "mining_context_status": mstatus, "worldcover_tile": tile["local_filename"], **sample_landcover(src, row.longitude, row.latitude)})
            if n % 100 == 0: LOG.info("%s: %d/%d hotspots", region.region_id, n, len(target))
    target = pd.concat([target, pd.DataFrame(additions)], axis=1)
    target["land_cover_code"] = target.land_cover_code.astype("Int64")
    label_function = extended_weak_label if extended else weak_label
    target = pd.concat([target, pd.DataFrame([label_function(r) for r in target.to_dict("records")])], axis=1)
    target = sorted_audit(target)
    if extended:
        target["training_context_complete"] = complete_context(target)
        target["label_context_eligible"] = target.weak_label.isin(TWO_CLASS) & target.training_context_complete
        target["training_eligible"] = target.label_context_eligible & target.persistence_history_complete
    return target, {"osm_source": provenance, "osm_geometry_audit": state}


def build_candidate(region, firms, tile):
    target, detail = build_feature_audit(region, firms, tile)
    osm_available = not target.industrial_context_status.eq("unavailable").any() and not target.mining_context_status.eq("unavailable").any()
    counts = target.weak_label.value_counts().reindex(LABELS, fill_value=0)
    summary = {"region_id": region.region_id, "total_june_hotspots": len(target), "active_dates": int(target.acq_date.nunique()), "day_count": int(target.day_night.eq("D").sum()), "night_count": int(target.day_night.eq("N").sum()), "osm_context_available": osm_available, **{k: int(v) for k, v in counts.items()}, "persistence_min": int(target.persistence_count_30d.min()), "persistence_median": float(target.persistence_count_30d.median()), "persistence_mean": float(target.persistence_count_30d.mean()), "persistence_max": int(target.persistence_count_30d.max()), **readiness(target.weak_label, osm_available)}
    summary["clipped_footprint_count"] = int(target.footprint_clipped_at_raster_edge.sum())
    summary["minimum_footprint_valid_fraction"] = float((target.footprint_valid_pixel_count / target.footprint_total_pixel_count).min())
    land_counts = {}
    for code, name in [(0, UNKNOWN), *CLASSES.items()]:
        count = int(target.land_cover_class.eq(name).sum())
        summary[f"landcover_{code}_count"] = count
        summary[f"landcover_{code}_pct"] = 100 * count / len(target)
        land_counts[name] = {"count": count, "percentage": 100 * count / len(target)}
    return target, summary, {**detail, "landcover_distribution": land_counts}


def decision(summaries):
    ready = [s for s in summaries if s["classifier_ready"]]
    return sorted(ready, key=lambda s: (s["largest_class_percentage"], -s["usable_labelled_rows"], s["region_id"]))[0]["region_id"] if ready else None


def report(summaries, details, manifest):
    winner = decision(summaries)
    lines = ["# Stage 3 final-region readiness decision", "", "Evaluation only; no classifier or final predictions have been created. All existing scope and previous-stage outputs are preserved.", ""]
    if winner:
        region = next(r for r in REGIONS if r.region_id == winner)
        lines += [f"Recommend exactly one region: **{region.min_lat}-{region.max_lat} N, {region.min_lon}-{region.max_lon} E ({winner})**, targeting **June 1-30, 2026**. This recommendation does not change the locked scope. Retain May 2-June 30 as the available history pool and use only each target's inclusive d-29 through d dates. June 1 starts May 3; May 2 is outside all June windows."]
    else:
        lines += ["**No final-region recommendation: neither candidate meets all fixed classifier-readiness thresholds.** Do not train a classifier or lower the thresholds automatically."]
    lines += ["", "If both qualify, prefer the lower largest-class percentage, then more usable labelled rows, then alphabetical region_id. Stage 2.5 suitability does not override readiness.", "", "| Metric | Candidate A: 15-16 N, 76-77 E | Candidate B: 21-22 N, 72-73 E |", "| --- | ---: | ---: |"]
    for key in ["total_june_hotspots", "active_dates", "day_count", "night_count", *LABELS, "persistence_min", "persistence_median", "persistence_mean", "persistence_max", "clipped_footprint_count", "minimum_footprint_valid_fraction", "usable_labelled_rows", "usable_class_count", "largest_class_percentage", "class_balance_ratio", "osm_context_available", "classifier_ready", "readiness_failures"]:
        lines.append(f"| {key} | {summaries[0][key]} | {summaries[1][key]} |")
    lines += ["", "## Source tiles and validation", "", "```json", json.dumps(manifest, indent=2, ensure_ascii=False), "```", "", "## Land-cover distributions and OSM audit", "", "```json", json.dumps(details, indent=2, ensure_ascii=False), "```", "", "## Limits and future evaluation", "", "These labels are proxy rules, not verified fire causes. Industrial distance and centre-pixel land cover generate the labels; using them as classifier inputs creates target leakage. A future split score measures weak-label agreement, not ground-truth accuracy. Consider a separate ablation excluding direct label-source features, including mining context and redundant/derived encodings. Neither model was trained here.", "", "WorldCover 2021 is static context for June 2026; land cover may have changed. FIRMS detections are not exact fire boundaries. The approximately 390 m window is a nominal approximation, not a real VIIRS footprint; pixel proportions use valid pixels only. OSM coverage can be incomplete, current rather than historical, and bbox-limited. Mining exclusions and renewable-power features can affect industrial proxy purity. Unmapped mining cannot be ruled out. Distinct detection dates do not measure complete satellite observation coverage. Unknown/Nodata remains separate; the exact industrial rule only excludes known Permanent water bodies. Conflict and unknown rows are never usable training labels.", "", "VNF is a blocked optional future source pending a separate data-use licence/application. No VNF download, adapter, match, or flare label was created."]
    lines += ["", "Clipped nominal footprints are flagged in the audits and counted above. Their proportions describe only the valid part inside the downloaded raster; they do not imply land-cover coverage beyond the edge. All target centre pixels are checked within raster bounds. No extra adjacent tile is downloaded solely to extend an audit footprint beyond the requested candidate coverage."]
    return "\n".join(lines) + "\n"


def osm_status_valid(status, distance):
    if status == "no_mapped_objects":
        return bool(pd.isna(distance))
    return bool(status == "available" and pd.notna(distance) and np.isfinite(distance) and distance >= 0)


def extended_weak_label(row):
    # A context prerequisite gates all proximity rules; failed queries cannot be absence.
    checked = dict(row)
    for prefix, distance_field in [("industrial", "distance_to_industrial_km"), ("mining", "nearest_mine_or_quarry_distance_km")]:
        if not osm_status_valid(checked[f"{prefix}_context_status"], checked[distance_field]):
            checked[f"{prefix}_context_status"] = "unavailable"
    result = weak_label(checked)
    # Tree/Shrubland and Cropland are disjoint centre codes, so Stage 3's order
    # gives the same result as wildfire before cropland after the first two rules.
    if result["weak_label"] == "agricultural_burn_candidate":
        result.update(weak_label="cropland_hotspot_candidate", weak_label_reason="Centre Cropland; industrial >1 km; mapped mining clear; no regional burning-season evidence; contextual only")
    return result


def complete_context(audit):
    result = []
    for row in audit.to_dict("records"):
        osm_valid = osm_status_valid(row["industrial_context_status"], row["distance_to_industrial_km"]) and osm_status_valid(row["mining_context_status"], row["nearest_mine_or_quarry_distance_km"])
        code = row["land_cover_code"]
        land_valid = pd.notna(code) and code in CLASSES and row["land_cover_sample_status"] == "valid" and row["land_cover_class"] == CLASSES[code]
        result.append(bool(osm_valid and land_valid))
    return pd.Series(result, index=audit.index, dtype=bool)


def eligible_context_mask(audit):
    return audit.weak_label.isin(TWO_CLASS) & complete_context(audit)


def monthly_distribution(audit):
    rows = []
    context = eligible_context_mask(audit)
    for period, end in [("2026-06", "2026-06-30"), ("2026-07", "2026-07-31"), ("2026-08", "2026-08-31"), ("2026-09", EXTENDED_END)]:
        selected = audit.acq_date.between(period + "-01", end)
        subset = audit.loc[selected]
        counts = subset.weak_label.value_counts().reindex(EXTENDED_LABELS, fill_value=0)
        rows.append({"period": period, "period_start": period + "-01", "period_end": end, "total_hotspots": len(subset), **{k: int(v) for k, v in counts.items()}, "persistence_history_incomplete": int((~subset.persistence_history_complete).sum()), "eligible_context_rows": int(context.loc[selected].sum()), "eligible_training_rows": int((context.loc[selected] & subset.persistence_history_complete).sum())})
    return pd.DataFrame(rows)


def class_concentration(pool):
    result = {}
    for label in TWO_CLASS:
        dates = pool.loc[pool.weak_label.eq(label), "acq_date"]
        counts = dates.str[:7].value_counts().sort_index()
        result[label] = {"monthly_counts": {k: int(v) for k, v in counts.items()}, "maximum_month_percentage": float(100 * counts.max() / len(dates)) if len(dates) else None}
    return result


def extended_readiness(audit):
    pool = audit.loc[eligible_context_mask(audit)]
    counts = pool.weak_label.value_counts().reindex(TWO_CLASS, fill_value=0)
    total = len(pool)
    history_count = int(pool.persistence_history_complete.sum())
    training = pool.loc[pool.persistence_history_complete]
    history_pct = 100 * history_count / total if total else 0.0
    largest_pct = float(100 * counts.max() / total) if total else None
    concentration = class_concentration(pool)
    conditions = {
        "1_industrial_complete_context_at_least_20": bool(counts[TWO_CLASS[0]] >= 20),
        "2_wildfire_complete_context_at_least_20": bool(counts[TWO_CLASS[1]] >= 20),
        "3_total_eligible_context_at_least_50": total >= 50,
        "4_largest_class_at_most_90_percent": largest_pct is not None and largest_pct <= 90,
        "5_all_eligible_context_valid": total > 0 and bool(complete_context(pool).all()),
        "6_eligible_history_complete_at_least_80_percent": total > 0 and history_pct >= 80,
        "7_each_class_month_concentration_at_most_80_percent": all(item["maximum_month_percentage"] is not None and item["maximum_month_percentage"] <= 80 for item in concentration.values()),
    }
    return {"can_lock_region": all(conditions.values()), "conditions": conditions, "eligible_context_counts": {k: int(v) for k, v in counts.items()}, "eligible_context_rows": total, "eligible_training_counts": {k: int(training.weak_label.eq(k).sum()) for k in TWO_CLASS}, "eligible_training_rows": len(training), "largest_class_percentage": largest_pct, "eligible_history_complete_rows": history_count, "eligible_history_complete_percentage": history_pct, "class_month_concentration": concentration, "two_class_candidates_excluded_for_invalid_context": int((audit.weak_label.isin(TWO_CLASS) & ~complete_context(audit)).sum())}


def cached_worldcover_tile(region):
    """Read-only Stage 3.5 acquisition: never download or rewrite a manifest."""
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != "v200" or manifest["product_name"] != "ESA WorldCover 10 m 2021 Map":
        raise ValueError("Wrong cached WorldCover product/version")
    index_record = manifest["grid"]
    index = RAW / index_record["local_filename"]
    if index.stat().st_size != index_record["file_size"] or checksum(index) != index_record["sha256"]:
        raise ValueError("Cached WorldCover grid integrity mismatch; downloads forbidden")
    tile_id, info = next(iter(required_tiles(validate_grid(index), [region]).items()))
    tile = next(t for t in manifest["tiles"] if t["tile_id"] == tile_id and region.region_id in t["candidate_regions"])
    path = RAW / tile["local_filename"]
    if path.stat().st_size != tile["file_size"] or checksum(path) != tile["sha256"]:
        raise ValueError("Cached WorldCover tile integrity mismatch; downloads forbidden")
    validate_tile(path, info["bounds"])
    LOG.info("Validated read-only WorldCover cache: %s", path.name)
    return tile


def extended_report(audit, distribution, result, provenance):
    lines = ["# Stage 3.5 extended-window decision", "", "Scope evaluated: **21.0-22.0 N, 72.0-73.0 E**, target **June 1-September 10, 2026** inclusive. One region and one continuous target window; May is persistence history only.", ""]
    lines += ["**PASS: this region and continuous window can be locked for the two-class industrial/wildfire scope.**" if result["can_lock_region"] else "**FAIL: this region/window cannot be locked under the fixed two-class readiness requirements.**"]
    lines += ["", "No classifier or final predictions were created. This is a data-readiness decision about proxy labels, not verification of fire cause.", "", "## Methodology correction", "", "Stage 3's agricultural_burn_candidate rule used cropland without a regional burning-season condition. That does not satisfy the locked cropland-plus-burning-season methodology. Stage 3.5 uses cropland_hotspot_candidate as audit context only. No burning-season calendar is invented, no cropland proxy is assigned agburn, and no historical Stage 3 file is rewritten. The current classifier scope contains only industrial and wildfire; the locked output field contract is unchanged.", "", "## Label and history coverage", "", f"Total target hotspots: {len(audit)}; active dates: {audit.acq_date.nunique()}; day/night: {int(audit.day_night.eq('D').sum())}/{int(audit.day_night.eq('N').sum())}.", "", "| Weak label | Count |", "| --- | ---: |"]
    for label in EXTENDED_LABELS:
        lines.append(f"| {label} | {int(audit.weak_label.eq(label).sum())} |")
    complete = int(audit.persistence_history_complete.sum())
    lines += ["", f"Persistence history complete: {complete}/{len(audit)} ({100 * complete / len(audit):.2f}%); incomplete: {len(audit)-complete}. Eligible-context history completeness: {result['eligible_history_complete_percentage']:.2f}%.", "", "For every acquisition date d the window is [d-29 days, d], both inclusive: exactly 30 calendar dates. June 1 starts May 3. September 10 starts August 12. Count distinct detection dates per fixed 0.01-degree grid cell; same-day detections count once. Only actual normalized observations contribute. Completeness describes the available dataset calendar range (May 1-September 10), not proof of daily satellite coverage or daily detections. No pre-May observations are assumed.", "", "## Monthly distribution", "", "| Period | Total | Industrial | Wildfire | Cropland context | Conflict | Unknown | Context unavailable | History incomplete | Eligible training |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in distribution.to_dict("records"):
        name = row["period"] + (" (1-10 only)" if row["period"] == "2026-09" else "")
        fields = ["total_hotspots", *EXTENDED_LABELS, "persistence_history_incomplete", "eligible_training_rows"]
        lines.append("| " + name + " | " + " | ".join(str(row[k]) for k in fields) + " |")
    lines += ["", "## Seven fixed readiness conditions", "", "Counts, balance and month concentration use the complete-OSM/valid-centre-land-cover two-class pool (label_context_eligible). The 80% history check uses that pool before filtering history, so the check is not made tautological. training_eligible additionally requires complete persistence history: incomplete rows stay in the audit but are excluded from later training by default.", "", "| Condition | Result |", "| --- | --- |"]
    lines.extend(f"| {key} | {'PASS' if value else 'FAIL'} |" for key, value in result["conditions"].items())
    lines += ["", "```json", json.dumps(result, indent=2, allow_nan=False), "```", "", "## Provenance and limitations", "", "```json", json.dumps(provenance, indent=2, ensure_ascii=False, allow_nan=False), "```", "", "All inputs are existing local caches; Stage 3.5 makes no new external-data requests and never rewrites raw files or earlier outputs. Missing/invalid OSM cache or failed geometry reconstruction is context-unavailable, never proof that no industrial or mining object exists. Missing or invalid WorldCover data stops clearly. A successful OSM query without mapped objects is still not proof of real-world absence.", "", "WorldCover 2021 is static context for 2026 detections; the centre class remains the label source. FIRMS pixels are not fire boundaries; the nominal 390 m footprint is approximate. Distances reuse Stage 2's ellipsoidal nearest-geometry method and 1 km heuristic. OSM is incomplete, bbox-limited and not necessarily contemporary with the fire detections. Unmapped mining and unrelated burning near industry may contaminate weak labels. Unknown land cover cannot enter the eligible pool, even if a proximity-based industrial candidate is recorded in the audit.", "", f"Nominal footprints clipped at the tile edge: {int(audit.footprint_clipped_at_raster_edge.sum())}; all are flagged and their proportions use valid pixels only. Persistence min/median/mean/max: {audit.persistence_count_30d.min()}/{audit.persistence_count_30d.median()}/{audit.persistence_count_30d.mean():.6f}/{audit.persistence_count_30d.max()}.", "", "Industrial distance, mining distance and land cover generate labels. Using direct label-source features as inputs creates target leakage. Later scores must be called weak-label agreement, not ground-truth accuracy; consider an ablation excluding direct/derived label-source features and a temporal/spatial split. Month concentration is a coverage check, not independent-event evidence. VNF remains an optional blocked source pending a separate licence/application; no flare labels are assigned.", "", "Outputs sort deterministically by acq_date, acq_time, latitude, longitude, hotspot_id and contain no changing timestamps. SHA-256 of the audit and distribution are below; the decision report's own full-file hash must be calculated externally to avoid a self-referential checksum.", "", "```json", json.dumps({"region_21_22_72_73_extended_audit.csv": hashlib.sha256(csv_text(audit).encode()).hexdigest(), "extended_window_label_distribution.csv": hashlib.sha256(csv_text(distribution).encode()).hexdigest()}, indent=2), "```"]
    return "\n".join(lines) + "\n"


def extended_artifacts():
    region = REGIONS[1]
    tile = cached_worldcover_tile(region)
    path = ROOT / "data/processed/firms_normalized.csv"
    firms = pd.read_csv(path, dtype={"hotspot_id": "string", "acq_date": "string", "acq_time": "string", "version": "string"})
    if firms.hotspot_id.isna().any() or not firms.hotspot_id.is_unique or not firms.acq_time.str.fullmatch(r"[0-9]{4}").all():
        raise ValueError("Invalid normalized hotspot IDs/acquisition times")
    audit, detail = build_feature_audit(region, firms, tile, EXTENDED_START, EXTENDED_END, AVAILABLE_START, extended=True)
    distribution = monthly_distribution(audit)
    result = extended_readiness(audit)
    provenance = {"normalized_input_sha256": checksum(path), "available_calendar_start": max(AVAILABLE_START, firms.acq_date.min()), "available_calendar_end": firms.acq_date.max(), "worldcover_tile": tile, **detail}
    contents = {
        "data/processed/region_21_22_72_73_extended_audit.csv": csv_text(audit).encode("utf-8"),
        "outputs/extended_window_label_distribution.csv": csv_text(distribution).encode("utf-8"),
        "outputs/extended_window_decision.md": extended_report(audit, distribution, result, provenance).encode("utf-8"),
    }
    return contents, result


def main_extended():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        contents, result = extended_artifacts()
        for relative, content in contents.items():
            (ROOT / relative).write_bytes(content)
        print(json.dumps({"readiness": result, "output_sha256": {p: hashlib.sha256(b).hexdigest() for p, b in contents.items()}}, indent=2))
    except Exception as exc:
        (ROOT / "outputs/extended_window_decision.md").write_text(f"# Stage 3.5 blocked\n\n{exc}\n\nRegion cannot be locked. No new external data or dummy replacement. No classifier or predictions. Do not use outputs from an earlier successful run as results of this failed run.\n", encoding="utf-8")
        LOG.exception("Offline Stage 3.5 failed")
        raise


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        manifest = acquire_worldcover()
        firms = pd.read_csv(ROOT / "data/processed/firms_normalized.csv", dtype={"hotspot_id": "string", "acq_date": "string", "acq_time": "string", "version": "string"})
        if firms.hotspot_id.isna().any() or not firms.hotspot_id.is_unique:
            raise ValueError("Invalid Stage 1 hotspot identity")
        audits, summaries, details = [], [], {}
        for region in REGIONS:
            tile = next(t for t in manifest["tiles"] if region.region_id in t["candidate_regions"])
            audit, summary, detail = build_candidate(region, firms, tile)
            audits.append(audit); summaries.append(summary); details[region.region_id] = detail
        for region, audit in zip(REGIONS, audits):
            (ROOT / f"data/processed/{region.region_id}_landcover_audit.csv").write_text(csv_text(audit), encoding="utf-8")
        (ROOT / "outputs/landcover_region_comparison.csv").write_text(csv_text(pd.DataFrame(summaries)), encoding="utf-8")
        (ROOT / "outputs/final_region_decision.md").write_text(report(summaries, details, manifest), encoding="utf-8")
        print(json.dumps(summaries, indent=2))
        print("Recommendation:", decision(summaries) or "NONE: readiness thresholds not met")
    except Exception as exc:
        (ROOT / "outputs/final_region_decision.md").write_text(f"# Stage 3 blocked\n\n{exc}\n\nNo final-region recommendation. No classifier or predictions created. Do not use prior Stage 3 outputs as results of this failed run.\n", encoding="utf-8")
        LOG.exception("Stage 3 stopped without dummy data")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extended", action="store_true", help="Offline Stage 3.5: June 1-September 10, region 21-22 N / 72-73 E; write only new extended outputs")
    args = parser.parse_args()
    main_extended() if args.extended else main()
