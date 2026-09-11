"""Stage 2: observed-date persistence and real, cached Overpass context only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import logging
from pathlib import Path
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
import requests
import shapely
from shapely.geometry import Point, Polygon, LineString, MultiPolygon
from shapely.ops import polygonize_full, unary_union

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://overpass-api.de/api/interpreter"
GEOD = Geod(ellps="WGS84")
BASE = ["hotspot_id", "latitude", "longitude", "acq_date", "acq_time", "frp", "brightness", "confidence", "day_night"]
INDUSTRIAL = {"landuse": {"industrial"}, "building": {"industrial"}, "man_made": {"works", "storage_tank", "flare", "petroleum_well"}, "power": {"plant"}, "industrial": None, "plant:source": None, "generator:source": None}
MINING = {"landuse": {"quarry"}, "man_made": {"mineshaft"}}
LOG = logging.getLogger("features")


def queries():
    result = {}
    for category, tags in [("industrial", INDUSTRIAL), ("mining", MINING)]:
        selectors = []
        for key, values in tags.items():
            for value in sorted(values) if values else [None]:
                condition = f'["{key}"="{value}"]' if value else f'["{key}"]'
                selectors.append(f"  nwr{condition}(23,86,24,87);")
        # Names are retained for all results; no name-only matching that could select shops/schools.
        result[category] = "[out:json][timeout:45];\n(\n" + "\n".join(selectors) + "\n);\nout body geom;\n"
    return result


def grid_id(lat, lon):
    # Decimal avoids floating-point floor errors at exact hundredth-degree edges.
    indices = [int((Decimal(str(v)) * 100).to_integral_value(rounding=ROUND_FLOOR)) for v in (lat, lon)]
    return f"g001_{indices[0]}_{indices[1]}"


def persistence(history, targets):
    unique = history[["grid_cell_id", "acq_date"]].drop_duplicates()
    dates = {cell: np.sort(pd.to_datetime(group.acq_date).to_numpy(dtype="datetime64[D]")) for cell, group in unique.groupby("grid_cell_id")}
    values = []
    for row in targets.itertuples():
        end = np.datetime64(row.acq_date, "D")
        days = dates.get(row.grid_cell_id, np.array([], dtype="datetime64[D]"))
        values.append(int(np.searchsorted(days, end, side="right") - np.searchsorted(days, end - np.timedelta64(29, "D"), side="left")))
    return pd.Series(values, index=targets.index, dtype="int64")


def select_rows(path):
    frame = pd.read_csv(path, dtype={"hotspot_id": "string", "acq_time": "string", "version": "string", "acq_date": "string"})
    if frame.hotspot_id.isna().any() or not frame.hotspot_id.is_unique:
        raise ValueError("Stage 1 IDs must be present and unique")
    if not frame.acq_time.str.fullmatch(r"[0-9]{4}").all():
        raise ValueError("Stage 1 acquisition times must be four-digit strings")
    history = frame.loc[frame.latitude.between(23, 24, inclusive="left") & frame.longitude.between(86, 87, inclusive="left") & frame.acq_date.between("2026-05-01", "2026-06-30"), BASE].copy()
    history["grid_cell_id"] = [grid_id(a, b) for a, b in zip(history.latitude, history.longitude)]
    targets = history.loc[history.acq_date.between("2026-06-01", "2026-06-30")].copy().sort_values(["acq_date", "acq_time", "hotspot_id"]).reset_index(drop=True)
    if targets.empty:
        raise ValueError("No June target hotspots in the locked demo area")
    targets["persistence_count_30d"] = persistence(history, targets)
    return history, targets


def valid_payload(content):
    payload = json.loads(content)
    if payload.get("remark") or not isinstance(payload.get("elements"), list):
        raise ValueError(f"Incomplete/error Overpass response: {payload.get('remark', 'missing elements')}")
    return payload


def fetch(category, query, raw_dir, state, refresh=False, session=None, sleep=time.sleep):
    session = session or requests.Session()
    key = hashlib.sha256((ENDPOINT + query).encode()).hexdigest()[:16]
    manifest = raw_dir / f"{category}_{key}_manifest.json"
    if manifest.exists() and not refresh:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        content = (raw_dir / meta["response_file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != meta["sha256"]:
            raise ValueError(f"Cached {category} response hash mismatch")
        payload = valid_payload(content)
        state["requests"].append({**meta, "category": category, "status": "cache_hit"})
        return payload
    for attempt in range(1, 4):
        entry = {"category": category, "endpoint": ENDPOINT, "attempt": attempt, "utc": datetime.now(timezone.utc).isoformat()}
        try:
            LOG.info("Overpass %s attempt %d/3", category, attempt)
            response = session.post(ENDPOINT, data={"data": query}, timeout=(15, 60), headers={"User-Agent": "SIH26162-local-feature-pipeline/2", "Accept-Encoding": "identity"})
            # Store every received response body as bytes before parsing, including errors.
            filename = f"{category}_{key}_{time.time_ns()}_attempt{attempt}.json"
            (raw_dir / filename).write_bytes(response.content)
            entry.update(http_status=response.status_code, response_file=filename)
            response.raise_for_status()
            payload = valid_payload(response.content)
            entry.update(status="success", sha256=hashlib.sha256(response.content).hexdigest())
            state["requests"].append(entry)
            manifest.write_text(json.dumps(entry, indent=2), encoding="utf-8")
            return payload
        except (requests.RequestException, ValueError) as exc:
            entry.update(status="failed", error=str(exc))
            state["requests"].append(entry)
            LOG.warning("%s", exc)
            if attempt < 3:
                sleep(2 ** attempt)
    raise RuntimeError(f"OSM {category} unavailable after 3 attempts; no feature outputs published. See coverage report.")


def matches(tags, rules):
    return any(k in tags and (values is None or tags[k] in values) for k, values in rules.items())


def is_mining(tags):
    return matches(tags, MINING) or tags.get("industrial") in {"mine", "mining", "quarry", "coal_mine"} or tags.get("man_made") in {"mine", "adit"}


def coordinates(geometry):
    pts = [(p["lon"], p["lat"]) for p in geometry]
    if not all(np.isfinite(x) and np.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90 for x, y in pts):
        raise ValueError("Invalid coordinates")
    return pts


def element_geometry(element):
    kind = element["type"]
    if kind == "node":
        return Point(coordinates([element])[0])
    if kind == "way":
        pts = coordinates(element.get("geometry", []))
        if len(pts) < 4 or pts[0] != pts[-1] or element.get("tags", {}).get("area") == "no":
            raise ValueError("Open/linear way is not an industrial polygon")
        geometry = Polygon(pts)
    elif kind == "relation":
        if element.get("tags", {}).get("type") not in {"multipolygon", "boundary"}:
            raise ValueError("Unsupported non-area relation")
        rings = {}
        for role in ["outer", "inner"]:
            lines = []
            for member in element.get("members", []):
                if member.get("role", "") == role or (role == "outer" and member.get("role", "") == ""):
                    if member.get("type") != "way":
                        raise ValueError("Nested/non-way area member unsupported")
                    pts = coordinates(member.get("geometry", []))
                    if len(pts) < 2:
                        raise ValueError("Missing relation member geometry")
                    lines.append(LineString(pts))
            polygons, cuts, dangles, invalid = polygonize_full(lines)
            if not cuts.is_empty or not dangles.is_empty or not invalid.is_empty:
                raise ValueError("Incomplete relation rings")
            rings[role] = unary_union(polygons)
        if rings["outer"].is_empty or not rings["outer"].covers(rings["inner"]) and not rings["inner"].is_empty:
            raise ValueError("Missing outer ring or inner ring outside outer")
        geometry = rings["outer"].difference(rings["inner"])
    else:
        raise ValueError("Unsupported OSM element type")
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Invalid polygon; not silently repaired")
    return geometry


def convert(payloads, state):
    elements = {}
    tag_counts, selector_counts = {}, {}
    for category, payload in payloads.items():
        counter = Counter()
        rules = INDUSTRIAL if category == "industrial" else MINING
        for e in payload["elements"]:
            tags = e.get("tags", {})
            for key, values in rules.items():
                if key in tags and (values is None or tags[key] in values):
                    counter[f"{key}={tags[key]}"] += 1
            elements[(e["type"], e["id"])] = e
        tag_counts[category] = dict(sorted(counter.items()))
        selector_counts[category] = {
            f"{key}={value if value is not None else '*'}": sum(
                key in e.get("tags", {}) and (value is None or e["tags"][key] == value)
                for e in payload["elements"]
            ) for key, values in rules.items() for value in (sorted(values) if values else [None])
        }
    rows, rejected = [], []
    for (kind, oid), element in sorted(elements.items()):
        tags = element.get("tags", {})
        mining = is_mining(tags)
        if not mining and not matches(tags, INDUSTRIAL):
            continue
        try:
            geometry = element_geometry(element)
            rows.append({"osm_id": f"{kind}/{oid}", "name": tags.get("name") or tags.get("name:en"), "asset_type": ";".join(f"{k}={tags[k]}" for k in ["landuse", "building", "man_made", "power", "industrial", "plant:source", "generator:source"] if k in tags), "osm_tags": json.dumps(tags, sort_keys=True, ensure_ascii=False), "is_mining": mining, "geometry": geometry})
        except (ValueError, KeyError, shapely.errors.GEOSException) as exc:
            rejected.append({"osm_id": f"{kind}/{oid}", "reason": str(exc)})
    gdf = gpd.GeoDataFrame(rows, columns=["osm_id", "name", "asset_type", "osm_tags", "is_mining", "geometry"], geometry="geometry", crs="EPSG:4326")
    # Polygon overlap with mapped mining areas excludes ambiguous industrial areas/points.
    # This conservative choice prevents mine-site industrial tags from seeding candidates.
    mine_geoms = list(gdf.loc[gdf.is_mining.eq(True), "geometry"])
    excluded = []
    if mine_geoms:
        mine_union = unary_union(mine_geoms)
        for idx, row in gdf.loc[gdf.is_mining.eq(False)].iterrows():
            if row.geometry.intersects(mine_union):
                excluded.append(row.osm_id)
    state.update(retrieved_counts={k: len(v["elements"]) for k, v in payloads.items()}, retrieved_tag_counts=tag_counts, retrieved_selector_counts=selector_counts, retrieved_named_counts={k: sum(bool(e.get("tags", {}).get("name") or e.get("tags", {}).get("name:en")) for e in v["elements"]) for k, v in payloads.items()}, rejected_geometries=rejected, mining_overlap_excluded=excluded, osm_timestamps={k: v.get("osm3s", {}).get("timestamp_osm_base") for k, v in payloads.items()})
    industrial = gdf.loc[gdf.is_mining.eq(False) & ~gdf.osm_id.isin(excluded)].copy().reset_index(drop=True)
    mines = gdf.loc[gdf.is_mining.eq(True)].copy().reset_index(drop=True)
    state["valid_feature_counts"] = {"industrial": len(industrial), "mining": len(mines), "industrial_geometry_types": industrial.geom_type.value_counts().to_dict(), "mining_geometry_types": mines.geom_type.value_counts().to_dict()}
    return industrial, mines


def densify_ring(ring, max_segment_m=100):
    result = []
    pts = list(ring.coords)
    for a, b in zip(pts[:-1], pts[1:]):
        distance = GEOD.inv(*a, *b)[2]
        n = max(0, int(np.ceil(distance / max_segment_m)) - 1)
        result.append(a)
        if n:
            result.extend(GEOD.npts(*a, *b, n))
    result.append(pts[-1])
    return result


def densify(geometry):
    if geometry.geom_type == "Point":
        return geometry
    if geometry.geom_type == "MultiPolygon":
        return MultiPolygon([densify(p) for p in geometry.geoms])
    return Polygon(densify_ring(geometry.exterior), [densify_ring(r) for r in geometry.interiors])


def nearest_asset(lon, lat, assets, dense=None):
    if assets.empty:
        return None, np.nan
    geometries = np.array([densify(g) for g in assets.geometry], dtype=object) if dense is None else dense
    # Ellipsoidal AEQD preserves geodesic radial distances from this hotspot.
    local_crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"
    forward = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    projected = shapely.transform(geometries, forward.transform, interleaved=False)
    origin = Point(0, 0)
    distances = shapely.distance(origin, projected)
    idx = int(np.argmin(distances))  # sorted OSM IDs give deterministic ties
    if distances[idx] < 1e-8:
        return assets.iloc[idx], 0.0
    segment = shapely.shortest_line(origin, projected[idx])
    x, y = list(segment.coords)[-1]
    inverse = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    near_lon, near_lat = inverse.transform(x, y)
    km = GEOD.inv(lon, lat, near_lon, near_lat)[2] / 1000
    return assets.iloc[idx], float(km)


def report(state):
    state["request_summary"] = dict(Counter(e["status"] for e in state["requests"]))
    text = "# OSM coverage report\n\n" + f"Run status: **{state['status']}**\n\n"
    text += "Exact queries (bbox south, west, north, east; current OSM snapshot):\n\n"
    for category, query in queries().items():
        text += f"## {category}\n\n```overpass\n{query}```\n\n"
    text += "## Execution and counts\n\n```json\n" + json.dumps(state, indent=2, ensure_ascii=False, allow_nan=False) + "\n```\n\n"
    text += "## Limitations\n\nOSM is incomplete and unevenly tagged. Current mapping is not a June 2026 historical snapshot. Counts are OSM objects, not deduplicated facilities; per-tag counts overlap. Names are preserved for tagged facilities; names alone do not establish industrial use. Invalid/open geometry and unsupported relations are excluded explicitly. Mining objects and industrial objects intersecting mapped mining geometry cannot seed candidates. Unmapped mines can still contaminate proximity evidence. The exact bbox query omits nearby assets outside it, and can miss enclosing ways with no vertex inside the box. Distances are to retrieved non-mining features only. Points locate an asset marker, not its footprint. Proximity is a conservative 1 km heuristic, not ground truth. Unknown rows are not negative labels. No final classes are assigned.\n\nData: © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright\n"
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-osm", action="store_true", help="Fetch a new snapshot; retain prior raw responses")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raw = ROOT / "data/raw/osm"
    raw.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "outputs/osm_coverage_report.md"
    source = ROOT / "data/processed/firms_normalized.csv"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    state = {"status": "running", "endpoint": ENDPOINT, "requests": [], "normalized_input_sha256": before}
    try:
        history, target = select_rows(source)
        state.update(june_targets=len(target), may_history_rows=int(history.acq_date.lt("2026-06-01").sum()), persistence_statistics=target.persistence_count_30d.describe().to_dict(), persistence_distribution={str(k): int(v) for k, v in target.persistence_count_30d.value_counts().sort_index().items()})
        LOG.info("June targets: %d; persistence: %s", len(target), state["persistence_statistics"])
        payloads = {}
        for category, query in queries().items():
            try:
                payloads[category] = fetch(category, query, raw, state, args.refresh_osm)
            finally:
                report_path.write_text(report(state), encoding="utf-8")
        industrial, mines = convert(payloads, state)
        if industrial.empty:
            raise RuntimeError("No usable non-mining industrial geometry; coverage inadequate for requested features")
        LOG.info("Usable industrial assets: %d; mining assets: %d", len(industrial), len(mines))
        dense_i = np.array([densify(g) for g in industrial.geometry], dtype=object)
        dense_m = np.array([densify(g) for g in mines.geometry], dtype=object)
        audit = []
        for i, row in enumerate(target.itertuples()):
            asset, distance = nearest_asset(row.longitude, row.latitude, industrial, dense_i)
            mine, mine_distance = nearest_asset(row.longitude, row.latitude, mines, dense_m)
            audit.append({"hotspot_id": row.hotspot_id, "grid_cell_id": row.grid_cell_id, "nearest_asset_osm_id": asset.osm_id, "nearest_asset_name": asset["name"], "nearest_asset_type": asset.asset_type, "nearest_asset_osm_tags": asset.osm_tags, "nearest_asset_distance_km": distance, "nearest_mine_or_quarry_osm_id": None if mine is None else mine.osm_id, "nearest_mine_or_quarry_distance_km": mine_distance, "industrial_candidate": "true" if distance <= 1.0 else "unknown"})
            if (i + 1) % 100 == 0:
                LOG.info("Computed %d/%d hotspot distances", i + 1, len(target))
        audit = pd.DataFrame(audit)
        target["distance_to_industrial_km"] = audit.nearest_asset_distance_km
        state.update(industrial_candidates=int(audit.industrial_candidate.eq("true").sum()), mine_context_available=int(audit.nearest_mine_or_quarry_distance_km.notna().sum()), mine_context_within_1km=int(audit.nearest_mine_or_quarry_distance_km.le(1).sum()))
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise RuntimeError("Stage 1 normalized input changed during execution")
        target[BASE + ["distance_to_industrial_km", "persistence_count_30d"]].to_csv(ROOT / "data/processed/june_feature_base.csv", index=False)
        audit.to_csv(ROOT / "data/processed/june_feature_audit.csv", index=False)
        state["status"] = "success"
        LOG.info("Success: %s", json.dumps({k: v for k, v in state.items() if k not in {"requests", "rejected_geometries", "retrieved_tag_counts"}}))
    except Exception as exc:
        state.update(status="FAILED", blocker=str(exc))
        LOG.exception("Stage 2 failed; do not use any outputs from an earlier run")
        raise
    finally:
        report_path.write_text(report(state), encoding="utf-8")


if __name__ == "__main__":
    main()
