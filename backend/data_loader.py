"""Validate the three tracked files once; never read pipeline data at API runtime."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from pydantic import TypeAdapter
from .config import DATA_DIR, DISCLAIMER, SOURCE_HASHES
from .models import AlertGroup, DistributionRow, Hotspot, Manifest, NumericSummary

CLASS_COUNTS = {"industrial": 308, "wildfire": 79, "unknown": 287}
RISK_COUNTS = {"critical": 0, "high": 10, "moderate": 149, "low": 515}
DEMO_FILES = ("demo_hotspots.json", "demo_alert_groups.json", "demo_manifest.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def strict_json(data: bytes) -> object:
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result
    return json.loads(data.decode("utf-8"), parse_constant=reject, object_pairs_hook=unique)


def rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def numeric_summary(values) -> NumericSummary:
    values = sorted(Decimal(str(v)) for v in values)
    n = len(values)
    return NumericSummary(minimum=float(values[0]), median=rounded((values[(n-1)//2]+values[n//2])/2),
                          mean=rounded(sum(values)/n), maximum=float(values[-1]))


def default_key(row: Hotspot):
    return row.acq_date, row.acq_time, row.hotspot_id


def alert_key(row: Hotspot):
    return -row.risk_score, -row.persistence_count_30d, -row.frp, *default_key(row)


def grid(value: float) -> int:
    return int((Decimal(str(value))/Decimal("0.05")).to_integral_value(rounding=ROUND_FLOOR))


def validate_content(hotspots: tuple[Hotspot, ...], groups: tuple[AlertGroup, ...], manifest: Manifest) -> None:
    if len(hotspots) != 674 or len({h.hotspot_id for h in hotspots}) != 674:
        raise ValueError("Snapshot must have 674 unique hotspots")
    if dict(Counter(h.predicted_class for h in hotspots)) != CLASS_COUNTS or manifest.class_counts.model_dump() != CLASS_COUNTS:
        raise ValueError("Locked class counts differ")
    if {b: sum(h.risk_band == b for h in hotspots) for b in RISK_COUNTS} != RISK_COUNTS or manifest.risk_band_counts.model_dump() != RISK_COUNTS:
        raise ValueError("Locked risk-band counts differ")
    source_order = lambda h: (h.acq_date, h.acq_time, h.latitude, h.longitude, h.hotspot_id)
    if list(hotspots) != sorted(hotspots, key=source_order):
        raise ValueError("Snapshot does not preserve Stage 5 source ordering")
    forbidden = ("confirmed industrial fire", "confirmed wildfire", "verified emergency", "dispatch immediately", "certain cause", "probability of fire", "predicted damage")
    for h in hotspots:
        expected = "critical" if h.risk_score >= 75 else "high" if h.risk_score >= 55 else "moderate" if h.risk_score >= 35 else "low"
        if h.risk_band != expected or any(term in h.explanation.lower() for term in forbidden):
            raise ValueError("Inconsistent band or unsafe explanation")
    alerts = sorted((h for h in hotspots if h.risk_band in {"high", "critical"}), key=alert_key)
    if len(alerts) != 10 or len(groups) != 6 or len({g.alert_group_id for g in groups}) != 6:
        raise ValueError("Expected ten alerts and six unique groups")
    expected_groups = {}
    for h in alerts:
        key = f"{h.acq_date.replace('-', '')}-{grid(h.latitude)}-{grid(h.longitude)}"
        expected_groups.setdefault(key, []).append(h)
    if set(expected_groups) != {g.alert_group_id for g in groups}:
        raise ValueError("Alert group IDs or membership differ")
    for g in groups:
        members = expected_groups[g.alert_group_id]
        representative = min(members, key=alert_key)
        lat, lon = grid(representative.latitude), grid(representative.longitude)
        bounds = tuple(rounded(Decimal(i)*Decimal('.05')) for i in [lat, lat+1, lon, lon+1])
        if (g.grid_min_latitude, g.grid_max_latitude, g.grid_min_longitude, g.grid_max_longitude) != bounds:
            raise ValueError("Incorrect fixed-grid summary bounds")
        if any(h.acq_date != g.acq_date for h in members) or g.hotspot_count != len(members):
            raise ValueError("Alert group crosses dates or counts differ")
        if any(getattr(g, c+"_count") != sum(h.predicted_class == c for h in members) for c in CLASS_COUNTS):
            raise ValueError("Group class counts differ")
        if g.maximum_risk_score != max(h.risk_score for h in members) or g.highest_risk_band != representative.risk_band or g.representative_hotspot_id != representative.hotspot_id:
            raise ValueError("Group representative or maximum differs")
        if g.maximum_persistence_count_30d != max(h.persistence_count_30d for h in members) or g.mean_frp != numeric_summary(h.frp for h in members).mean:
            raise ValueError("Group measurements differ")
    if list(groups) != sorted(groups, key=lambda g: (g.acq_date, g.grid_min_latitude, g.grid_min_longitude)):
        raise ValueError("Group ordering differs")
    expected_keys = [(c, b) for c in [*CLASS_COUNTS, "overall"] for b in [*RISK_COUNTS, "all"]]
    if [(r.predicted_class, r.risk_band) for r in manifest.risk_distribution] != expected_keys:
        raise ValueError("Distribution categories or order differ")
    for row in manifest.risk_distribution:
        selected = [h.risk_score for h in hotspots if (row.predicted_class == "overall" or h.predicted_class == row.predicted_class) and (row.risk_band == "all" or h.risk_band == row.risk_band)]
        actual = (row.minimum_score, row.median_score, row.mean_score, row.maximum_score)
        expected = tuple(numeric_summary(selected).model_dump().values()) if selected else (None,)*4
        if row.hotspot_count != len(selected) or actual != expected:
            raise ValueError("Stage 5 distribution does not reconcile")


@dataclass(frozen=True)
class Dataset:
    hotspots: tuple[Hotspot, ...]
    alert_groups: tuple[AlertGroup, ...]
    manifest: Manifest
    by_id: Mapping[str, Hotspot]


def validate_snapshot(contents: Mapping[str, bytes]) -> Dataset:
    if set(contents) != set(DEMO_FILES):
        raise ValueError("Snapshot requires exactly three tracked JSON files")
    for data in contents.values():
        strict_json(data)
    manifest = Manifest.model_validate_json(contents["demo_manifest.json"], strict=True)
    if manifest.disclaimer != DISCLAIMER or not manifest.limitations:
        raise ValueError("Missing or inconsistent disclaimer/limitations")
    if len(manifest.source_file_hashes) != 5 or {h.filename: h.sha256 for h in manifest.source_file_hashes} != SOURCE_HASHES:
        raise ValueError("Manifest Stage 5 source hashes differ")
    expected = {name: sha(contents[name]) for name in DEMO_FILES[:2]}
    if len(manifest.exported_file_hashes) != 2 or {h.filename: h.sha256 for h in manifest.exported_file_hashes} != expected:
        raise ValueError("Manifest exported hashes differ or contain self-reference")
    hotspots = TypeAdapter(tuple[Hotspot, ...]).validate_json(contents["demo_hotspots.json"], strict=True)
    groups = TypeAdapter(tuple[AlertGroup, ...]).validate_json(contents["demo_alert_groups.json"], strict=True)
    validate_content(hotspots, groups, manifest)
    return Dataset(hotspots, groups, manifest, MappingProxyType({h.hotspot_id: h for h in hotspots}))


def load_dataset(directory: Path = DATA_DIR) -> Dataset:
    try:
        return validate_snapshot({name: (directory/name).read_bytes() for name in DEMO_FILES})
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Tracked demo-data startup validation failed: {exc}") from exc
