"""Export authenticated Stage 5 values verbatim into a small tracked JSON snapshot."""
from __future__ import annotations
import csv
import io
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.config import CLASSIFICATION_SOURCE, DISCLAIMER, SOURCE_HASHES
from backend.data_loader import DEMO_FILES, alert_key, json_bytes, sha, validate_snapshot
from backend.models import AlertGroup, DistributionRow, Hotspot, Manifest

CLASSIFIED_FIELDS = "hotspot_id latitude longitude acq_date acq_time frp brightness confidence day_night distance_to_industrial_km persistence_count_30d land_cover_class predicted_class class_probability risk_score risk_band".split()
AUDIT_FIELDS = "hotspot_id predicted_class frp persistence_count_30d normalized_confidence normalized_day_night frp_points persistence_points confidence_points night_points risk_score risk_band primary_risk_driver explanation".split()
ALERT_FIELDS = "alert_id hotspot_id latitude longitude acq_date acq_time predicted_class frp persistence_count_30d risk_score risk_band frp_points persistence_points confidence_points night_points primary_risk_driver explanation".split()
GROUP_FIELDS = list(AlertGroup.model_fields)
DIST_FIELDS = list(DistributionRow.model_fields)
COMPONENT_FIELDS = ["frp_points", "persistence_points", "confidence_points", "night_points", "primary_risk_driver", "explanation"]
FLOAT_FIELDS = {"latitude", "longitude", "frp", "brightness", "distance_to_industrial_km", "risk_score", "frp_points", "persistence_points", "confidence_points", "night_points", "grid_min_latitude", "grid_max_latitude", "grid_min_longitude", "grid_max_longitude", "maximum_risk_score", "mean_frp", "minimum_score", "median_score", "mean_score", "maximum_score"}
INT_FIELDS = {"persistence_count_30d", "hotspot_count", "industrial_count", "wildfire_count", "unknown_count", "maximum_persistence_count_30d"}


def read_csv(data: bytes, columns: list[str]) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    if reader.fieldnames != columns:
        raise ValueError("Stage 5 source schema differs from locked contract")
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError("Malformed source CSV")
    return rows


def typed(row: dict[str, str]) -> dict:
    return {key: None if value == "" else float(value) if key in FLOAT_FIELDS else int(value) if key in INT_FIELDS else value for key,value in row.items()}


def build_export(root: Path = ROOT) -> dict[str, bytes]:
    sources = {name: (root/name).read_bytes() for name in SOURCE_HASHES}
    for name,data in sources.items():
        if sha(data) != SOURCE_HASHES[name]:
            raise ValueError(f"Stage 5 source SHA-256 mismatch: {name}; stop without repair")
    classified,audits,alerts,groups,distribution = [read_csv(data,columns) for data,columns in zip(sources.values(),[CLASSIFIED_FIELDS,AUDIT_FIELDS,ALERT_FIELDS,GROUP_FIELDS,DIST_FIELDS])]
    if len(classified) != 674 or len(audits) != 674 or len({r['hotspot_id'] for r in audits}) != 674:
        raise ValueError("Stage 5 source counts/IDs differ")
    hotspots = []
    for row,audit in zip(classified,audits):
        for key in set(row) & set(audit):
            if row[key] != audit[key]:
                raise ValueError(f"Audit join/order/value mismatch: {key}")
        if audit["normalized_confidence"] != {"l":"low","n":"nominal","h":"high"}[row["confidence"]] or audit["normalized_day_night"] != {"D":"day","N":"night"}[row["day_night"]]:
            raise ValueError("Audit sensor categories differ")
        fields = {**typed(row), "classification_source":CLASSIFICATION_SOURCE, **typed({k:audit[k] for k in COMPONENT_FIELDS})}
        hotspots.append(Hotspot.model_validate(fields, strict=True))
    by_id = {h.hotspot_id:h for h in hotspots}
    ranked = sorted((h for h in hotspots if h.risk_band in {"high","critical"}),key=alert_key)
    if [r['hotspot_id'] for r in alerts] != [h.hotspot_id for h in ranked] or len(alerts) != 10:
        raise ValueError("Stage 5 alert selection/order differs")
    for row in alerts:
        h=by_id[row['hotspot_id']]
        if row['alert_id'] != 'ALT-'+h.hotspot_id or typed({k:v for k,v in row.items() if k!='alert_id'}) != h.model_dump(include=set(ALERT_FIELDS)-{'alert_id'}):
            raise ValueError("Alert fields differ from hotspot/audit values")
    group_models = tuple(AlertGroup.model_validate(typed(r),strict=True) for r in groups)
    dist_models = tuple(DistributionRow.model_validate(typed(r),strict=True) for r in distribution)
    contents = {"demo_hotspots.json":json_bytes([h.model_dump() for h in hotspots]),
                "demo_alert_groups.json":json_bytes([g.model_dump() for g in group_models])}
    manifest = Manifest(
        schema_version="1.0.0", generated_from_stage=5, generated_at_policy="omitted_for_deterministic_export",
        dataset_mode="retrospective_demo", region_bounds=dict(min_latitude=21.0,max_latitude=24.0,min_longitude=72.0,max_longitude=75.0,boundary_policy="south_west_inclusive_north_east_exclusive"),
        period=dict(date_from="2026-06-01",date_to="2026-06-30"),total_hotspots=674,
        class_counts=dict(industrial=308,wildfire=79,unknown=287),risk_band_counts=dict(critical=0,high=10,moderate=149,low=515),
        high_priority_alert_count=10,daily_alert_group_count=6,classification_source=CLASSIFICATION_SOURCE,classifier_operational=False,
        source_file_hashes=tuple(dict(filename=name,sha256=value) for name,value in SOURCE_HASHES.items()),
        exported_file_hashes=tuple(dict(filename=name,sha256=sha(value)) for name,value in contents.items()),
        risk_distribution=dist_models,limitations=(
            "Retrospective June 2026 demonstration; no live NASA feed or external-service connection.",
            "Classes are imperfect rule-based weak-label context; Stage 4 classifiers failed the operational gate and are not used.",
            "Review priority uses fixed Stage 5 heuristics; routine persistent heat can rank highly and low priority does not establish safety.",
            "FIRMS locations are coarse detections, not fire perimeters; daily grid groups are not incident boundaries.",
            "Persistence is retrospective through the acquisition date and can include later same-day observations.",
            "OSM coverage is incomplete and WorldCover 2021 may differ from 2026 land cover; no external alerts are sent.",
        ),disclaimer=DISCLAIMER)
    contents["demo_manifest.json"] = json_bytes(manifest.model_dump(mode="json"))
    validate_snapshot(contents)
    if any((root/name).read_bytes()!=data for name,data in sources.items()):
        raise RuntimeError("Source changed while exporting; stop")
    return contents


def export(root: Path = ROOT) -> dict[str,str]:
    contents=build_export(root)
    destination=root/"backend/data"
    destination.mkdir(parents=True,exist_ok=True)
    for name,data in contents.items():
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode="wb",dir=destination,prefix=".stage6-",suffix=".tmp",delete=False) as stream:
                temporary=Path(stream.name)
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,destination/name)
        finally:
            if temporary is not None and temporary.exists(): temporary.unlink()
    if any(sha((root/name).read_bytes())!=value for name,value in SOURCE_HASHES.items()):
        raise RuntimeError("Source preservation check failed")
    return {name:sha(data) for name,data in contents.items()}


if __name__=="__main__":
    print(json_bytes(export()).decode(),end="")
