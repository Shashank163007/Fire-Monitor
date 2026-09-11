"""Read-only Stage 2.5 region recommendation using FIRMS and one OSM query per cell."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import time

# Preserve prior-stage bytecode even when someone omits the documented -B flag.
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import requests

if __package__:
    from .build_features import ENDPOINT, INDUSTRIAL, MINING, convert, densify, matches, nearest_asset, valid_payload
else:
    from build_features import ENDPOINT, INDUSTRIAL, MINING, convert, densify, matches, nearest_asset, valid_payload

ROOT = Path(__file__).resolve().parents[1]
START, END = "2026-05-01", "2026-09-10"
DAYS = (pd.Timestamp(END) - pd.Timestamp(START)).days + 1
COLUMNS = "region_id min_lat max_lat min_lon max_lon hotspot_count active_dates day_count night_count industrial_feature_count mining_feature_count pct_near_industrial pct_near_mining osm_query_status suitability_score selection_rank".split()
LOG = logging.getLogger("region_scan")


def read_firms(path):
    frame = pd.read_csv(path, dtype={"hotspot_id": "string", "acq_date": "string", "acq_time": "string", "version": "string"})
    frame = frame.loc[frame.acq_date.between(START, END)].copy()
    if frame.empty or not frame.hotspot_id.is_unique:
        raise ValueError("Expected nonempty FIRMS data with unique hotspot IDs")
    if not np.isfinite(frame[["latitude", "longitude"]]).all().all():
        raise ValueError("Invalid FIRMS coordinates")
    frame["min_lat"] = np.floor(frame.latitude).astype(int)
    frame["min_lon"] = np.floor(frame.longitude).astype(int)
    return frame


def select_candidates(frame, limit=6):
    if not 1 <= limit <= 6:
        raise ValueError("Candidate limit must be between 1 and 6")
    f = frame.loc[frame.acq_date.between(START, END)].copy()
    f["min_lat"] = np.floor(f.latitude).astype(int)
    f["min_lon"] = np.floor(f.longitude).astype(int)
    f["day"] = f.day_night.eq("D")
    f["night"] = f.day_night.eq("N")
    summary = f.groupby(["min_lat", "min_lon"], as_index=False).agg(hotspot_count=("hotspot_id", "size"), active_dates=("acq_date", "nunique"), day_count=("day", "sum"), night_count=("night", "sum"))
    summary = summary.loc[summary.hotspot_count.ge(100) & summary.active_dates.ge(10)].copy()
    summary["screen_score"] = (summary.hotspot_count.rank(method="average", pct=True) + summary.active_dates.rank(method="average", pct=True) + (summary.day_count.gt(0) & summary.night_count.gt(0)).astype(float)) / 3
    summary["max_lat"] = summary.min_lat + 1
    summary["max_lon"] = summary.min_lon + 1
    summary["region_id"] = [f"cell_{a}_{b}" for a, b in zip(summary.min_lat, summary.min_lon)]
    return summary.sort_values(["screen_score", "hotspot_count", "active_dates", "region_id"], ascending=[False, False, False, True]).head(limit).reset_index(drop=True)


def clamp_component(value):
    if pd.isna(value):
        raise ValueError("Missing component input must not become invented OSM evidence")
    return float(np.clip(value, 0, 1))


def score_components(active_dates, day_count, night_count, pct_industrial,
                     industrial_features, pct_mining, max_active_dates,
                     osm_query_status="success"):
    """Normalize the positive subtotal first; subtract the unscaled mining penalty."""
    both = day_count > 0 and night_count > 0
    either = day_count > 0 or night_count > 0
    success = osm_query_status == "success"
    inputs = {
        "active_date_score": clamp_component(active_dates / max_active_dates if max_active_dates > 0 else 0),
        "day_night_score": clamp_component(1.0 if both else 0.5 if either else 0.0),
        "industrial_proximity_score": clamp_component(pct_industrial / 100),
        "osm_availability_score": clamp_component((1.0 if industrial_features > 0 else 0.5) if success else 0.0),
        "mining_dominance_score": clamp_component(pct_mining / 100),
    }
    components = {
        "active_date_component": 30 * inputs["active_date_score"],
        "day_night_component": 20 * inputs["day_night_score"],
        "industrial_proximity_component": 25 * inputs["industrial_proximity_score"],
        "osm_availability_component": 15 * inputs["osm_availability_score"],
    }
    positive_subtotal = sum(components.values())
    normalized_positive_score = (positive_subtotal / 90) * 100
    mining_penalty = 30 * inputs["mining_dominance_score"]
    suitability_score = round(max(0, min(100, normalized_positive_score - mining_penalty)), 2)
    return {**inputs, **components, "positive_subtotal": positive_subtotal,
            "normalized_positive_score": normalized_positive_score,
            "mining_penalty": mining_penalty, "suitability_score": suitability_score}


def score(active_dates, day_count, night_count, pct_industrial, industrial_features,
          pct_mining, max_active_dates, osm_query_status="success"):
    return score_components(active_dates, day_count, night_count, pct_industrial,
                            industrial_features, pct_mining, max_active_dates,
                            osm_query_status)["suitability_score"]


def query_for(row):
    bbox = f"({int(row.min_lat)},{int(row.min_lon)},{int(row.max_lat)},{int(row.max_lon)})"
    selectors = []
    for rules in [INDUSTRIAL, MINING]:
        for key, values in rules.items():
            for value in sorted(values) if values else [None]:
                condition = f'["{key}"="{value}"]' if value else f'["{key}"]'
                selectors.append(f"  nwr{condition}{bbox};")
    return "[out:json][timeout:45];\n(\n" + "\n".join(selectors) + "\n);\nout body geom;\n"


def fetch_cell(row, raw_dir, detail, session=None, sleep=time.sleep):
    query = query_for(row)
    prefix = row.region_id + "_" + hashlib.sha256((ENDPOINT + query).encode()).hexdigest()[:16]
    detail.update(endpoint=ENDPOINT, query=query, requests=[])
    # Successful cached response filenames encode HTTP status, fetch UTC, and query hash.
    for path in sorted(raw_dir.glob(prefix + "_*_http200.json"), reverse=True):
        content = path.read_bytes()
        try:
            payload = valid_payload(content)
        except (ValueError, TypeError):
            continue  # Raw partial/error responses are retained but never accepted.
        detail["requests"].append({"status": "cached", "file": path.name, "sha256": hashlib.sha256(content).hexdigest()})
        return payload
    session = session or requests.Session()
    for attempt in range(1, 4):
        record = {"attempt": attempt, "utc": datetime.now(timezone.utc).isoformat()}
        try:
            LOG.info("%s Overpass attempt %d/3", row.region_id, attempt)
            response = session.post(ENDPOINT, data={"data": query}, headers={"User-Agent": "SIH26162-region-scan/2.5", "Accept-Encoding": "identity"}, timeout=(15, 60))
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            path = raw_dir / f"{prefix}_{stamp}_attempt{attempt}_http{response.status_code}.json"
            path.write_bytes(response.content)
            record.update(file=path.name, http_status=response.status_code, sha256=hashlib.sha256(response.content).hexdigest())
            response.raise_for_status()
            payload = valid_payload(response.content)
            record["status"] = "success"
            detail["requests"].append(record)
            return payload
        except (requests.RequestException, ValueError) as exc:
            record.update(status="failed", error=str(exc))
            detail["requests"].append(record)
            LOG.warning("%s: %s", row.region_id, exc)
            if attempt < 3:
                sleep(2 ** attempt)
    return None


def proximity(frame, industrial, mining):
    dense_i = np.array([densify(g) for g in industrial.geometry], dtype=object)
    dense_m = np.array([densify(g) for g in mining.geometry], dtype=object)
    memo, flags_i, flags_m = {}, [], []
    for n, row in enumerate(frame.itertuples(), 1):
        key = (row.longitude, row.latitude)
        if key not in memo:
            _, di = nearest_asset(*key, industrial, dense_i)
            _, dm = nearest_asset(*key, mining, dense_m)
            # Empty, successfully queried asset pools mean zero matches to retrieved objects.
            memo[key] = (bool(di <= 1), bool(dm <= 1))
        i, m = memo[key]
        flags_i.append(i)
        flags_m.append(m)
        if n % 500 == 0:
            LOG.info("Distance progress: %d/%d", n, len(frame))
    result = frame.copy()
    result["near_industrial"], result["near_mining"] = flags_i, flags_m
    return result


def monthly_options(frame, industrial_count):
    options = []
    # Only complete target months with the entire previous calendar month available.
    for month in ["2026-06", "2026-07", "2026-08"]:
        period = pd.Period(month, freq="M")
        subset = frame.loc[frame.acq_date.str.startswith(month)]
        if subset.empty:
            continue
        previous = str(period - 1)
        di, ni = int(subset.day_night.eq("D").sum()), int(subset.day_night.eq("N").sum())
        near_i, near_m = int(subset.near_industrial.sum()), int(subset.near_mining.sum())
        active = int(subset.acq_date.nunique())
        options.append({"target_month": month, "history_month": previous, "hotspots": len(subset), "active_dates": active, "day_count": di, "night_count": ni, "near_industrial": near_i, "near_mining": near_m, "pct_near_industrial": 100 * near_i / len(subset), "pct_near_mining": 100 * near_m / len(subset), "both_contexts": int((subset.near_industrial & subset.near_mining).sum()), "history_rows": int(frame.acq_date.str.startswith(previous).sum()), "preferred_evidence": active >= 10 and di > 0 and ni > 0 and 0 < near_i < len(subset)})
    maximum = max((m["active_dates"] for m in options), default=0)
    for option in options:
        option["max_active_dates_among_month_options"] = maximum
        option["month_score"] = score(option["active_dates"], option["day_count"], option["night_count"], option["pct_near_industrial"], industrial_count, option["pct_near_mining"], maximum)
    return sorted(options, key=lambda m: (-int(m["preferred_evidence"]), -m["month_score"], -m["pct_near_industrial"], m["pct_near_mining"], -m["active_dates"], m["target_month"]))


def ranked(rows):
    table = pd.DataFrame(rows)
    # Explicit eligibility prevents even a stale numeric score from ranking a failure.
    table.loc[table.osm_query_status.ne("success"), "suitability_score"] = np.nan
    table = table.sort_values(["suitability_score", "pct_near_industrial", "pct_near_mining", "active_dates", "region_id"], ascending=[False, False, True, False, True], na_position="last").reset_index(drop=True)
    table["selection_rank"] = pd.Series(pd.NA, index=table.index, dtype="Int64")
    available = table.suitability_score.notna()
    table.loc[available, "selection_rank"] = np.arange(1, int(available.sum()) + 1)
    return table[COLUMNS]


def score_candidates(rows, details):
    successful = [r for r in rows if r["osm_query_status"] == "success"]
    maximum = max((r["active_dates"] for r in successful), default=0)
    for row in rows:
        detail = details[row["region_id"]]
        detail["max_active_dates_among_successful_candidates"] = maximum
        if row["osm_query_status"] != "success":
            row["suitability_score"] = np.nan
            detail["scoring_status"] = "unavailable: missing OSM evidence; excluded from normalization and recommendation"
            continue
        components = score_components(row["active_dates"], row["day_count"], row["night_count"], row["pct_near_industrial"], row["industrial_feature_count"], row["pct_near_mining"], maximum)
        row["suitability_score"] = components["suitability_score"]
        detail["score_components"] = components
    return ranked(rows)


def recommendation_candidates(table, details):
    ordered = ranked(table.to_dict("records"))
    return [r for r in ordered.itertuples() if r.osm_query_status == "success" and pd.notna(r.selection_rank) and details[r.region_id].get("months")]


def write_report(table, details, source_hash, eligible_cells, protected_ok):
    lines = ["# Demo region recommendation (Stage 2.5)", "", "Recommendation only: the locked Stage 2 region and all prior files remain unchanged. No classifier, final classes, land-cover/VNF download, or frontend is created.", "", f"FIRMS period: {START} through {END} ({DAYS} calendar days). Eligible 1-degree cells: {eligible_cells}; scanned: {len(table)}. Input SHA-256: `{source_hash}`.", "", "## Ranked comparison", "", "Percentages describe detections within 1 km of retrieved context, not verified fire causes. Unavailable candidates are unranked, not assigned zero suitability.", "", "| Rank | Region (south/west cell origin) | Hotspots | Dates | Day / night | Industrial / mining objects | Near industrial % | Near mining % | Score | Status |", "| --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |"]
    for r in table.itertuples():
        def value(x):
            return "unavailable" if pd.isna(x) else f"{x:.2f}"
        lines.append(f"| {r.selection_rank if pd.notna(r.selection_rank) else '-'} | {r.region_id} | {r.hotspot_count} | {r.active_dates} | {r.day_count} / {r.night_count} | {value(r.industrial_feature_count)} / {value(r.mining_feature_count)} | {value(r.pct_near_industrial)} | {value(r.pct_near_mining)} | {value(r.suitability_score)} | {r.osm_query_status} |")
    choices = recommendation_candidates(table, details)
    if choices:
        winner = choices[0]
        month = details[winner.region_id]["months"][0]
        period = pd.Period(month["target_month"], freq="M")
        previous = period - 1
        lines += ["", "## Exactly one recommendation", "", f"Recommend **{winner.min_lat} <= latitude < {winner.max_lat}, {winner.min_lon} <= longitude < {winner.max_lon}**, region **{winner.region_id}**, with **{period.start_time.date()} through {period.end_time.date()}** as target dates. Retain **{previous.start_time.date()} through {previous.end_time.date()} only as prior-month persistence history**. Target-month observations also contribute to each trailing 30-day count. Do not use other months as target rows or persistence history after adopting this recommendation.", "", f"This is the highest-ranked successfully scanned cell with an eligible complete target month. Target month: {month['hotspots']} hotspots, {month['active_dates']} active dates, {month['day_count']} day and {month['night_count']} night observations; {month['near_industrial']} ({month['pct_near_industrial']:.2f}%) near non-mining industrial objects and {month['near_mining']} ({month['pct_near_mining']:.2f}%) near mining objects. Both contexts: {month['both_contexts']}; previous-month history rows: {month['history_rows']}.", "", f"The existing June region has 75/736 (10.19%) near industrial context and 659/736 (89.54%) near mining context. The recommended target month's observed mining percentage is {month['pct_near_mining']:.2f}% and industrial percentage is {month['pct_near_industrial']:.2f}%. Lower mapped mining proximity reduces that specific confound; presence of industrial-proximate and other detections supports later comparison. Other detections remain unknown, not confirmed natural fires. Region extents differ, so these figures are screening evidence, not a controlled causal comparison; both target-month figures refer to June 2026.", "", "OSM proximity is weak-label evidence, not ground truth. This recommendation is a better-supported demo starting point, not proof of industrial-versus-natural class separability."]
        if not month["preferred_evidence"]:
            lines += ["", "Caution: the selected month does not meet every preferred evidence criterion; manual review is necessary before adopting it."]
        lines += ["", "## Target-month comparison for the recommended cell", "", "May is excluded as a target because April history is absent; September is incomplete. Region ranking uses the full period; month selection separately normalizes active dates to the maximum among that cell's complete-month options.", "", "```json", json.dumps(details[winner.region_id]["months"], indent=2), "```"]
    else:
        lines += ["", "## Blocker", "", "No successfully queried candidate with a complete target-month option is available. A defensible recommendation cannot be made; rerun after Overpass is accessible. No result was fabricated."]
    lines += ["", "## Method and limitations", "", "See `docs/region_selection_method.md` for exact screening and score formulas. All five component inputs are clamped to [0,1]. Score = round(clip(((30*A + 20*B + 25*I + 15*F)/90)*100 - 30*M, 0, 100), 2). A uses the maximum active dates among successful candidates; B is 1/0.5/0 for both/one/no valid day-night categories; F is 1/0.5/0 for successful usable industrial features/successful empty industrial features/failed query. The maximum positive score is 100 and the mining penalty is at most 30. Failed queries remain in the comparison with null score/rank and are ineligible. Ties use score descending, industrial percentage descending, mining percentage ascending, active dates descending, region ID alphabetically. It is demo suitability only, never fire risk or ML output.", "", "OSM is incomplete, current rather than historical, and unevenly tagged. One exact bbox query per cell omits external nearby assets and can miss enclosing polygons without vertices inside. Geometry conversion and conservative mining-overlap exclusions follow Stage 2 unchanged. Counts are OSM objects, not independent facilities. Points are markers; large industrial polygons may cover unrelated thermal sources. Successfully empty industrial or mining results mean no retrieved matching context, not verified absence of infrastructure or mines. Coarse VIIRS geolocation, observation gaps, numerical distance approximation, day/night imbalance, and selection using this dataset limit later proxy-label interpretation. The six-cell screen is not an exhaustive search. No land-cover evidence verifies natural fire categories. OSM: © OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright).", "", f"Pre-existing Stage 1/2 inputs and outputs unchanged during script execution: **{protected_ok}**.", "", "## Exact queries, requests, and geometry audit", ""]
    for region, detail in details.items():
        lines += [f"### {region}", "", "```overpass", detail["query"].rstrip(), "```", "", "```json", json.dumps({k: v for k, v in detail.items() if k != "query"}, indent=2, ensure_ascii=False), "```", ""]
    (ROOT / "outputs/demo_region_selection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bool(choices)


def protected_hashes():
    paths = []
    for directory in ["data", "src", "tests", "docs", "outputs"]:
        for p in (ROOT / directory).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and "region_scan" not in p.parts and p.name not in {"scan_demo_regions.py", "test_region_selection.py", "demo_region_comparison.csv", "demo_region_selection.md", "region_selection_method.md"}:
                paths.append(p)
    paths.extend(ROOT / name for name in ["README.md", "requirements.txt", ".gitignore", "pytest.ini"])
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    before = protected_hashes()
    source = ROOT / "data/processed/firms_normalized.csv"
    frame = read_firms(source)
    candidates = select_candidates(frame)
    if candidates.empty:
        raise RuntimeError("No qualifying FIRMS cells")
    counts = frame.groupby(["min_lat", "min_lon"]).agg(n=("hotspot_id", "size"), dates=("acq_date", "nunique"))
    eligible = int((counts.n.ge(100) & counts.dates.ge(10)).sum())
    raw = ROOT / "data/raw/osm/region_scan"
    raw.mkdir(parents=True, exist_ok=True)
    rows, details = [], {}
    LOG.info("Selected cells:\n%s", candidates.to_string(index=False))
    for candidate in candidates.itertuples():
        detail = {"screen_score": candidate.screen_score}
        details[candidate.region_id] = detail
        row = {k: getattr(candidate, k) for k in COLUMNS[:9]}
        row.update({k: np.nan for k in COLUMNS[9:]})
        payload = fetch_cell(candidate, raw, detail)
        if payload is None:
            row["osm_query_status"] = "unavailable"
        else:
            industrial_payload = {"elements": [e for e in payload["elements"] if matches(e.get("tags", {}), INDUSTRIAL)]}
            mining_payload = {"elements": [e for e in payload["elements"] if matches(e.get("tags", {}), MINING)]}
            geometry_state = {}
            industrial, mining = convert({"industrial": industrial_payload, "mining": mining_payload}, geometry_state)
            detail.update(geometry_audit=geometry_state, osm_timestamp=payload.get("osm3s", {}).get("timestamp_osm_base"), retrieved_unique_objects=len(payload["elements"]))
            local = frame.loc[frame.min_lat.eq(candidate.min_lat) & frame.min_lon.eq(candidate.min_lon)].copy()
            flags = proximity(local, industrial, mining)
            pi, pm = float(flags.near_industrial.mean() * 100), float(flags.near_mining.mean() * 100)
            row.update(industrial_feature_count=len(industrial), mining_feature_count=len(mining), pct_near_industrial=pi, pct_near_mining=pm, osm_query_status="success")
            detail["months"] = monthly_options(flags, len(industrial))
            LOG.info("%s: industrial %.2f%%; mining %.2f%%; score pending successful-candidate denominator", candidate.region_id, pi, pm)
        rows.append(row)
    after = protected_hashes()
    if before != after:
        raise RuntimeError("A protected Stage 1/2 file changed")
    comparison = score_candidates(rows, details)
    comparison.to_csv(ROOT / "outputs/demo_region_comparison.csv", index=False)
    recommended = write_report(comparison, details, hashlib.sha256(source.read_bytes()).hexdigest(), eligible, True)
    print(comparison.to_string(index=False))
    if not recommended:
        raise SystemExit(1)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
