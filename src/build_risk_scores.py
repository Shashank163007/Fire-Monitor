"""Stage 5: offline, deterministic human-review priority, using no classifier."""
from __future__ import annotations

import builtins
from contextlib import contextmanager, ExitStack
import csv
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_EVEN
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
STAGE4_HASH = "b5d0840a9e8f0865fc6d1972c23e21b98a8294efcf5e5453cb5b443b3314373f"
CLASSIFIED = "data/processed/classified_hotspots.csv"
CONTRACT = "hotspot_id latitude longitude acq_date acq_time frp brightness confidence day_night distance_to_industrial_km persistence_count_30d land_cover_class predicted_class class_probability risk_score risk_band".split()
CLASSES = ["industrial", "wildfire", "unknown"]
COUNTS = dict(zip(CLASSES, [308, 79, 287]))
BANDS = ["critical", "high", "moderate", "low"]
COMPONENTS = ["frp_points", "persistence_points", "confidence_points", "night_points"]
DRIVERS = ["thermal_intensity", "persistence", "observation_confidence", "night_observation"]
AUDIT_FIELDS = "hotspot_id predicted_class frp persistence_count_30d normalized_confidence normalized_day_night frp_points persistence_points confidence_points night_points risk_score risk_band primary_risk_driver explanation".split()
ALERT_FIELDS = "alert_id hotspot_id latitude longitude acq_date acq_time predicted_class frp persistence_count_30d risk_score risk_band frp_points persistence_points confidence_points night_points primary_risk_driver explanation".split()
SUMMARY_FIELDS = "alert_group_id acq_date grid_min_latitude grid_max_latitude grid_min_longitude grid_max_longitude hotspot_count maximum_risk_score highest_risk_band industrial_count wildfire_count unknown_count mean_frp maximum_persistence_count_30d representative_hotspot_id group_explanation".split()
DISTRIBUTION_FIELDS = "predicted_class risk_band hotspot_count minimum_score median_score mean_score maximum_score".split()
CSV_PATHS = [CLASSIFIED, "outputs/hotspot_risk_audit.csv", "outputs/high_priority_alerts.csv", "outputs/daily_alert_summary.csv", "outputs/risk_score_distribution.csv"]
NEW_PATHS = set(CSV_PATHS[1:] + ["src/build_risk_scores.py", "tests/test_risk_scoring.py", "docs/risk_scoring_specification.md", "outputs/risk_scoring_methodology.md", "outputs/risk_scoring_validation.md"])
DISCLAIMER = "This deterministic score ranks FIRMS thermal detections for human review. It is not a probability, verified severity measurement, fire-cause determination or emergency-dispatch recommendation."
D = Decimal
LOG = logging.getLogger("risk_scoring")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def parse_csv(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    if reader.fieldnames != CONTRACT:
        raise ValueError("Classified input must contain exactly the 16 ordered contract columns")
    rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed CSV record")
    return rows


def number(value, field):
    try:
        result = D(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}: missing or nonnumeric value {value!r}") from None
    if not result.is_finite():
        raise ValueError(f"{field}: nonfinite value {value!r}")
    return result


def clip(value, maximum):
    return min(D(maximum), max(D(0), value))


def fixed(value, places=2):
    return format(D(value).quantize(D(1).scaleb(-places), rounding=ROUND_HALF_EVEN), "f")


def compact(value):
    text = fixed(value, 12).rstrip("0").rstrip(".")
    return text or "0"


def frp_points(value):
    value = number(value, "frp")
    if value < 0:
        raise ValueError("frp must be nonnegative")
    if value <= 5:
        points = D(0)
    elif value <= 20:
        points = (value - 5) / 15 * 10
    elif value <= 50:
        points = 10 + (value - 20) / 30 * 15
    elif value <= 100:
        points = 25 + (value - 50) / 50 * 10
    else:
        points = 35 + min((value - 100) / 100, D(1)) * 5
    return clip(points, 40)


def persistence_points(value):
    value = number(value, "persistence_count_30d")
    if value != value.to_integral_value() or not 1 <= value <= 30:
        raise ValueError("persistence_count_30d must be an integer in [1,30]")
    return clip((value - 1) / 29 * 30, 30)


def confidence_value(value):
    """Return canonical sensor category/value, review points and validity status."""
    text = "" if value is None else str(value).strip().lower()
    categories = {"l": ("low", 5), "low": ("low", 5), "n": ("nominal", 12),
                  "nominal": ("nominal", 12), "h": ("high", 20), "high": ("high", 20)}
    if text in categories:
        category, points = categories[text]
        return category, clip(D(points), 20), "valid"
    try:
        numeric = number(text, "confidence")
        if 0 <= numeric <= 100:
            return compact(numeric), clip(numeric / 100, 1) * 20, "valid"
    except ValueError:
        pass
    return "unknown", D(0), "missing" if not text else "unexpected"


def day_night_value(value):
    text = "" if value is None else str(value).strip().lower()
    if text in {"n", "night"}:
        return "night", D(10), "valid"
    if text in {"d", "day"}:
        return "day", D(0), "valid"
    return "unknown", D(0), "missing" if not text else "unexpected"


def band(score):
    score = number(score, "risk_score")
    return "critical" if score >= 75 else "high" if score >= 55 else "moderate" if score >= 35 else "low"


def primary_driver(points):
    # max returns the first maximum, implementing the required tie order.
    return DRIVERS[max(range(4), key=lambda i: points[i])]


def score_inputs(frp, persistence, confidence, day_night):
    """Only these four arguments can affect numeric score; context is excluded."""
    conf, cp, conf_status = confidence_value(confidence)
    dn, np, dn_status = day_night_value(day_night)
    points = [frp_points(frp), persistence_points(persistence), clip(cp, 20), clip(np, 10)]
    score = clip(sum(points), 100).quantize(D("0.01"), rounding=ROUND_HALF_EVEN)
    return {**dict(zip(COMPONENTS, points)), "normalized_confidence": conf,
            "normalized_day_night": dn, "confidence_status": conf_status, "day_night_status": dn_status,
            "risk_score": score, "risk_band": band(score), "primary_risk_driver": primary_driver(points)}


def explanation(row, scored):
    phrases = {
        "thermal_intensity": "elevated FRP" if scored["frp_points"] > 0 else "thermal detection",
        "persistence": f"persistent activity on {row['persistence_count_30d']} distinct dates",
        "observation_confidence": "high sensor confidence" if scored["normalized_confidence"] == "high" else "sensor confidence",
        "night_observation": "night-time observation",
    }
    points = ", ".join(f"{name} {fixed(scored[key])}" for name, key in zip(
        ["FRP", "persistence", "sensor confidence", "night observation"], COMPONENTS))
    return (f"{scored['risk_band'].capitalize()} review priority: {phrases[scored['primary_risk_driver']]}. "
            f"Points: {points}. Rule-based context category: {row['predicted_class']}.")


def validate_rows(rows, initial=True):
    if len(rows) != 674:
        raise ValueError("Expected exactly 674 hotspots; no row removal allowed")
    if any(list(row) != CONTRACT for row in rows):
        raise ValueError("Required ordered schema differs")
    ids = [r["hotspot_id"] for r in rows]
    if any(not x or not str(x).strip() for x in ids) or len(set(ids)) != 674:
        raise ValueError("Expected 674 unique non-null hotspot IDs")
    if {c: sum(r["predicted_class"] == c for r in rows) for c in CLASSES} != COUNTS:
        raise ValueError("Locked industrial/wildfire/unknown counts differ")
    for row in rows:
        if row["class_probability"] != "":
            raise ValueError("Every class_probability must remain null")
        if initial and (row["risk_score"] != "" or row["risk_band"] != ""):
            raise ValueError("Initial risk fields must be null")
        lat, lon = number(row["latitude"], "latitude"), number(row["longitude"], "longitude")
        if not (21 <= lat < 24 and 72 <= lon < 75):
            raise ValueError("Hotspot outside locked region")
        try:
            date = datetime.strptime(row["acq_date"], "%Y-%m-%d")
            time = datetime.strptime(row["acq_time"], "%H%M")
        except ValueError:
            raise ValueError("Invalid acquisition date or HHMM time") from None
        if date.strftime("%Y-%m-%d") != row["acq_date"] or not "2026-06-01" <= row["acq_date"] <= "2026-06-30":
            raise ValueError("Acquisition date outside June 2026")
        if time.strftime("%H%M") != row["acq_time"]:
            raise ValueError("Acquisition time must be zero-padded HHMM")
        frp_points(row["frp"])
        persistence_points(row["persistence_count_30d"])


def authenticate_input(data):
    rows = parse_csv(data)
    initial = digest(data) == STAGE4_HASH
    if not initial:
        # Reconstruct only the two originally empty columns; never repair source fields.
        original = [{**row, "risk_score": "", "risk_band": ""} for row in rows]
        if digest(csv_bytes(original, CONTRACT)) != STAGE4_HASH:
            raise ValueError("Stage 4 input SHA-256 mismatch; source values or order changed")
        if any(not r["risk_score"] or not r["risk_band"] for r in rows):
            raise ValueError("Unrecognized initial input or partially scored CSV; stop")
    validate_rows(rows, initial=initial)
    if not initial:
        for row in rows:
            scored = score_inputs(*(row[c] for c in ["frp", "persistence_count_30d", "confidence", "day_night"]))
            if row["risk_score"] != fixed(scored["risk_score"]) or row["risk_band"] != scored["risk_band"]:
                raise ValueError("Cached risk score/band differs from fresh deterministic calculation")
    return rows, "initial" if initial else "verified_cached"


def validate_operational_state(metrics):
    decision = metrics.get("decision", {})
    if decision.get("operational_method") != "rule_based_weak_label_fallback" or decision.get("classifier_passes") is not False:
        raise ValueError("Stage 4 rule-based fallback decision differs; stop")
    if decision.get("conditions", {}).get("mean_macro_f1_at_least_0_75") is not False or metrics.get("final_class_counts") != COUNTS:
        raise ValueError("Stage 4 gate/count conditions differ; stop")
    # These are classifier input encodings, not risk-point mappings. Verify their
    # documented meaning; never convert the ordinal values into Stage 5 points.
    mapping = metrics.get("confidence", {}).get("categorical_ordinal_mapping")
    if mapping != {"l/low": 0, "n/nominal": 1, "h/high": 2}:
        raise ValueError("Existing confidence encoding differs from documented Stage 4 mapping; review conflict")


def alert_key(row):
    return (-number(row["risk_score"], "risk_score"), -number(row["persistence_count_30d"], "persistence"),
            -number(row["frp"], "frp"), row["acq_date"], row["acq_time"], row["hotspot_id"])


def grid_index(value):
    return int((number(value, "coordinate") / D("0.05")).to_integral_value(rounding=ROUND_FLOOR))


def daily_summary(alerts):
    groups = {}
    for row in alerts:
        key = (row["acq_date"], grid_index(row["latitude"]), grid_index(row["longitude"]))
        groups.setdefault(key, []).append(row)
    output = []
    for (date, lat, lon), members in sorted(groups.items()):
        representative = min(members, key=alert_key)
        highest = min((r["risk_band"] for r in members), key=BANDS.index)
        output.append(dict(zip(SUMMARY_FIELDS, [
            f"{date.replace('-', '')}-{lat}-{lon}", date, fixed(D(lat)*D('.05')), fixed(D(lat+1)*D('.05')),
            fixed(D(lon)*D('.05')), fixed(D(lon+1)*D('.05')), len(members),
            fixed(max(D(r["risk_score"]) for r in members)), highest,
            *[sum(r["predicted_class"] == c for r in members) for c in CLASSES],
            fixed(sum(D(r["frp"]) for r in members)/len(members)),
            int(max(D(r["persistence_count_30d"]) for r in members)), representative["hotspot_id"],
            f"{len(members)} high/critical review-priority thermal detections on {date} in one fixed 0.05-degree summary cell. Representative hotspot: {representative['hotspot_id']}. This cell is not a fire perimeter or incident boundary."
        ])))
    return output


def distribution(rows):
    output = []
    for cls in CLASSES + ["overall"]:
        for risk_band in BANDS + ["all"]:
            scores = sorted(D(r["risk_score"]) for r in rows if (cls == "overall" or r["predicted_class"] == cls)
                            and (risk_band == "all" or r["risk_band"] == risk_band))
            n = len(scores)
            stats = [fixed(scores[0]), fixed((scores[(n-1)//2]+scores[n//2])/2), fixed(sum(scores)/n), fixed(scores[-1])] if n else [""]*4
            output.append(dict(zip(DISTRIBUTION_FIELDS, [cls, risk_band, n, *stats])))
    return output


def build_tables(rows):
    scored_rows, audit, alerts = [], [], []
    invalid = {f"{field}_{status}": 0 for field in ["confidence", "day_night"] for status in ["missing", "unexpected"]}
    observed = {field: {} for field in ["confidence", "day_night"]}
    for row in rows:
        scored = score_inputs(*(row[c] for c in ["frp", "persistence_count_30d", "confidence", "day_night"]))
        for field in observed:
            observed[field][row[field]] = observed[field].get(row[field], 0) + 1
            if scored[field+"_status"] != "valid":
                invalid[field+"_"+scored[field+"_status"]] += 1
        updated = {**row, "risk_score": fixed(scored["risk_score"]), "risk_band": scored["risk_band"]}
        details = {**updated, **{c: compact(scored[c]) for c in COMPONENTS},
                   "normalized_confidence": scored["normalized_confidence"], "normalized_day_night": scored["normalized_day_night"],
                   "primary_risk_driver": scored["primary_risk_driver"], "explanation": explanation(row, scored)}
        scored_rows.append(updated)
        audit.append({key: details[key] for key in AUDIT_FIELDS})
        if scored["risk_band"] in {"high", "critical"}:
            alerts.append({"alert_id": "ALT-"+row["hotspot_id"], **{key: details[key] for key in ALERT_FIELDS if key != "alert_id"}})
    alerts.sort(key=alert_key)
    tables = [scored_rows, audit, alerts, daily_summary(alerts), distribution(scored_rows)]
    validate_tables(rows, tables)
    return tables, {"observed_values": observed, "invalid_or_missing": {"frp": 0, "persistence_count_30d": 0, **invalid}}


def validate_tables(original, tables):
    scored, audit, alerts, summary, dist = tables
    if len(scored) != 674 or len(audit) != 674:
        raise ValueError("Output lost or duplicated rows")
    for before, after, detail in zip(original, scored, audit):
        if list(after) != CONTRACT or any(before[c] != after[c] for c in CONTRACT[:-2]):
            raise ValueError("Source fields, classes or row order changed")
        if detail["hotspot_id"] != after["hotspot_id"] or after["class_probability"]:
            raise ValueError("Audit order/probability invariant failed")
        score = number(after["risk_score"], "risk_score")
        if not 0 <= score <= 100 or band(score) != after["risk_band"]:
            raise ValueError("Invalid score or band")
    expected = {r["hotspot_id"] for r in scored if r["risk_band"] in {"high", "critical"}}
    if {r["hotspot_id"] for r in alerts} != expected or len(alerts) != len(expected) or alerts != sorted(alerts, key=alert_key):
        raise ValueError("Alert selection/order invariant failed")
    if sum(r["hotspot_count"] for r in summary) != len(alerts):
        raise ValueError("Summary total differs from alerts")
    if sum(r["hotspot_count"] for r in dist if r["predicted_class"] in CLASSES and r["risk_band"] in BANDS) != 674:
        raise ValueError("Distribution total differs from 674")


def protected_hashes(root=ROOT):
    excluded = NEW_PATHS | {CLASSIFIED, "README.md"}
    files = [p for folder in ["src", "tests", "docs", "outputs", "data", "models"] for p in (root/folder).rglob("*") if p.is_file()]
    files += [root/"requirements.txt"]
    return {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in files if p.relative_to(root).as_posix() not in excluded}


def assert_protected(before, root=ROOT):
    if before != protected_hashes(root):
        raise RuntimeError("Protected Stage 1-4 file integrity check failed")


@contextmanager
def execution_guard():
    """Reject network connections and model imports during Stage 5 execution."""
    counts = {"network_attempts": 0, "model_import_attempts": 0}
    original_import = builtins.__import__
    def no_network(*args, **kwargs):
        counts["network_attempts"] += 1
        raise RuntimeError("Stage 5 forbids network requests")
    def safe_import(name, *args, **kwargs):
        if name.split(".")[0] in {"joblib", "sklearn", "pickle"} or name == "src.train_classifier":
            counts["model_import_attempts"] += 1
            raise RuntimeError("Stage 5 forbids model loading/training imports")
        return original_import(name, *args, **kwargs)
    with ExitStack() as stack:
        for owner, attr in [(socket.socket, "connect"), (socket.socket, "connect_ex"), (socket.socket, "sendto"), (socket, "create_connection")]:
            stack.enter_context(patch.object(owner, attr, no_network))
        # Requests is not a Stage 5 dependency; also block dispatch if a caller loaded it.
        if "requests.sessions" in sys.modules:
            stack.enter_context(patch.object(sys.modules["requests.sessions"].Session, "request", no_network))
        stack.enter_context(patch.object(builtins, "__import__", safe_import))
        yield counts
        if any(counts.values()):
            raise RuntimeError("Forbidden operation attempted during Stage 5")


def atomic_publish(contents, root=ROOT):
    if set(contents) - (NEW_PATHS | {CLASSIFIED}):
        raise ValueError("Attempt to write outside Stage 5 output allowlist")
    # All artifacts are computed and validated before publishing any of them.
    for relative, data in contents.items():
        destination = root/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".stage5-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def reports(tables, validation, hashes, protected_count, guard_counts, root):
    methodology = (root/"docs/risk_scoring_specification.md").read_text(encoding="utf-8")
    methodology = "# Stage 5 risk scoring methodology\n\n" + methodology.split("\n", 1)[1].lstrip()
    counts = [{k: r[k] for k in ["predicted_class", "risk_band", "hotspot_count"]} for r in tables[4]]
    evidence = {"authenticated_stage4_input_sha256": STAGE4_HASH, "rows": len(tables[0]),
                "class_counts": COUNTS, "class_probability_nonnull_count": 0,
                "preserved_source_columns": CONTRACT[:-2], "original_row_order_preserved": True,
                "protected_file_count": protected_count, "protected_files_unchanged": True,
                "high_priority_hotspots": len(tables[2]), "daily_spatial_groups": len(tables[3]),
                "stage5_execution_guard": guard_counts, "models_loaded": 0, "classifiers_trained": 0,
                "alerts_transmitted": 0, **validation, "risk_band_counts": counts, "output_sha256": hashes}
    report = ("# Stage 5 risk scoring validation\n\n" + DISCLAIMER + "\n\n"
              "The original Stage 4 CSV is authenticated before writing. On a scored rerun, clearing ONLY the two risk columns must reproduce its exact SHA-256, and every existing score/band must match fresh calculation. Source strings and row order are preserved.\n\n"
              "The guard blocks network connections/HTTP dispatch and model imports. Models are never deserialized or invoked; binary bytes may be hashed solely for preservation. No external alerts are transmitted. The counts below describe this Stage 5 run, not classifier unit-test fixtures in the preserved earlier suite.\n\n"
              "```json\n" + json.dumps(evidence, indent=2, sort_keys=True) + "\n```\n\n"
              "Hashes above cover the five required CSVs. A report cannot include its own final hash without a self-reference; report hashes can be compared externally. No timestamp or first-run/cache status enters deterministic artifacts.\n\n"
              "Run the complete suite and the pipeline twice using README.md. Completed test results and cross-run checks are recorded in that Stage 5 validation record. Per-run integrity is checked before and after atomic publishing. Each file replacement is atomic; the group of files is not a transaction. If interrupted, rerun to regenerate a consistent set.\n")
    return {"outputs/risk_scoring_methodology.md": methodology.encode("utf-8"), "outputs/risk_scoring_validation.md": report.encode("utf-8")}


def run_pipeline(root=ROOT):
    root = Path(root)
    with execution_guard() as guard_counts:
        protected = protected_hashes(root)
        data = (root/CLASSIFIED).read_bytes()
        rows, mode = authenticate_input(data)
        LOG.info("Stage 4 input SHA-256 verified: %s (%s)", STAGE4_HASH, mode)
        metrics = json.loads((root/"outputs/classifier_metrics.json").read_bytes())
        validate_operational_state(metrics)
        tables, validation = build_tables(rows)
        fields = [CONTRACT, AUDIT_FIELDS, ALERT_FIELDS, SUMMARY_FIELDS, DISTRIBUTION_FIELDS]
        contents = {path: csv_bytes(table, columns) for path, table, columns in zip(CSV_PATHS, tables, fields)}
        hashes = {p: digest(b) for p, b in contents.items()}
        contents.update(reports(tables, validation, hashes, len(protected), dict(guard_counts), root))
        assert_protected(protected, root)
        if (root/CLASSIFIED).read_bytes() != data:
            raise RuntimeError("Classified input changed during execution; stop before publishing")
        atomic_publish(contents, root)
        assert_protected(protected, root)
        if any((root/p).read_bytes() != b for p, b in contents.items()):
            raise RuntimeError("Published output verification failed")
        return {"input_mode": mode, "stage4_input_sha256": STAGE4_HASH,
                "network_attempts": guard_counts["network_attempts"], "model_import_attempts": guard_counts["model_import_attempts"],
                "class_counts": COUNTS, "risk_band_counts": {b: sum(r["risk_band"] == b for r in tables[0]) for b in BANDS},
                "high_priority_hotspots": len(tables[2]), "daily_spatial_groups": len(tables[3]),
                "output_sha256": {p: digest(b) for p, b in contents.items()}}


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        print(json.dumps(run_pipeline(), indent=2, sort_keys=True))
    except Exception:
        LOG.exception("Stage 5 stopped; no silent input repair, relabelling or threshold changes")
        raise


if __name__ == "__main__":
    main()
