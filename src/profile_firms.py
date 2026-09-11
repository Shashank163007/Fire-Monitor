"""Offline profiling and deterministic normalization of the supplied VIIRS CSVs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KEY = ["satellite", "instrument", "latitude", "longitude", "acq_date", "acq_time"]
REQUIRED = KEY + ["brightness", "frp", "confidence", "daynight"]


def read_csv(path):
    # Reading as strings preserves UTC HHMM and product version exactly.
    frame = pd.read_csv(path, dtype="string")
    frame.columns = frame.columns.str.strip()
    if frame.columns.duplicated().any():
        raise ValueError(f"{path}: duplicate column names")
    for column in frame:
        frame[column] = frame[column].str.strip().replace("", pd.NA)
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns: {sorted(missing)}")
    return frame


def counts(series):
    return {str(k): int(v) for k, v in series.fillna("<missing>").value_counts().items()}


def numeric_profile(series):
    values = pd.to_numeric(series, errors="coerce")
    finite = values[np.isfinite(values.fillna(np.nan).astype(float))]
    stats = finite.describe(percentiles=[.01, .05, .25, .5, .75, .95, .99])
    return {
        "statistics": {k: None if pd.isna(v) else float(v) for k, v in stats.items()},
        "non_numeric_non_missing": int((series.notna() & values.isna()).sum()),
        "nonfinite_numeric": int((values.notna() & ~np.isfinite(values.astype(float))).sum()),
        "histogram": counts(pd.cut(finite, bins=10).astype("string")) if len(finite) else {},
    }


def profile(frame):
    dates = pd.to_datetime(frame.acq_date, format="%Y-%m-%d", errors="coerce")
    valid_dates = dates.dropna()
    date_counts = counts(frame.acq_date)
    calendar = pd.date_range(valid_dates.min(), valid_dates.max()) if len(valid_dates) else []
    return {
        "row_count": len(frame), "columns": list(frame.columns),
        "date_range": [str(valid_dates.min().date()), str(valid_dates.max().date())] if len(valid_dates) else [None, None],
        "invalid_or_missing_dates": int(dates.isna().sum()),
        "days_with_detections": int(valid_dates.nunique()),
        "dates_without_detections": [str(d.date()) for d in calendar if str(d.date()) not in date_counts],
        "coordinate_bounds": {c: numeric_profile(frame[c])["statistics"] for c in ["latitude", "longitude"]},
        "missing_values": {c: {"count": int(frame[c].isna().sum()), "percent": float(frame[c].isna().mean() * 100) if len(frame) else 0.0} for c in frame},
        "distributions": {"frp": numeric_profile(frame.frp), "brightness": numeric_profile(frame.brightness), "confidence": counts(frame.confidence), "daynight": counts(frame.daynight)},
        "metadata_distributions": {c: counts(frame[c]) for c in ["satellite", "instrument", "version", "type"] if c in frame},
        "exact_duplicate_rows_beyond_first": int(frame.duplicated().sum()),
        "observation_key_duplicate_rows_beyond_first": int(frame.duplicated(KEY).sum()),
        "daily_counts": dict(sorted(date_counts.items())),
    }


def normalize_one(frame, name, source):
    frame = frame.copy()
    frame["source_file"] = name
    frame["source_kind"] = source
    frame["source_row"] = np.arange(2, len(frame) + 2)  # CSV line including header
    reasons = pd.Series("", index=frame.index, dtype="string")

    def flag(mask, reason):
        nonlocal reasons
        reasons = reasons.mask(mask.fillna(True), reasons + reason + ";")

    dates = pd.to_datetime(frame.acq_date, format="%Y-%m-%d", errors="coerce")
    flag(dates.isna(), "invalid_acq_date")
    frame["acq_date"] = dates.dt.strftime("%Y-%m-%d").astype("string")
    time = frame.acq_time.str.zfill(4)
    flag(~time.str.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]", na=False), "invalid_acq_time")
    frame["acq_time"] = time
    for col in ["satellite", "instrument"]:
        frame[col] = frame[col].str.upper()
        flag(frame[col].isna(), f"missing_{col}")
    flag(frame.instrument.ne("VIIRS"), "unsupported_instrument")
    for col in ["latitude", "longitude", "brightness", "frp", "scan", "track", "bright_t31"]:
        if col not in frame:
            continue
        original = frame[col]
        value = pd.to_numeric(original, errors="coerce").astype("Float64")
        flag(original.notna() & (value.isna() | ~np.isfinite(value)), f"invalid_{col}")
        frame[col] = value
    flag(~frame.latitude.between(-90, 90) | frame.latitude.isna(), "latitude_out_of_bounds")
    flag(~frame.longitude.between(-180, 180) | frame.longitude.isna(), "longitude_out_of_bounds")
    flag(frame.frp.lt(0).fillna(False), "negative_frp")
    flag(frame.brightness.le(0).fillna(False), "nonpositive_brightness")
    frame["confidence"] = frame.confidence.str.lower()
    flag(frame.confidence.notna() & ~frame.confidence.isin(["l", "n", "h"]), "invalid_confidence")
    frame = frame.rename(columns={"daynight": "day_night"})
    frame["day_night"] = frame.day_night.str.upper()
    flag(frame.day_night.notna() & ~frame.day_night.isin(["D", "N"]), "invalid_day_night")
    raw_type = frame["type"] if "type" in frame else pd.Series(pd.NA, index=frame.index, dtype="string")
    numeric_type = pd.to_numeric(raw_type, errors="coerce")
    valid_type = numeric_type.isin([0, 1, 2, 3])
    flag(raw_type.notna() & ~valid_type, "invalid_type")
    frame["type"] = numeric_type.where(valid_type).astype("Int64")
    rejected = frame.loc[reasons.ne("")].copy()
    rejected["rejection_reason"] = reasons[reasons.ne("")]
    return frame.loc[reasons.eq("")].copy(), rejected


def normalize(frames):
    clean, rejected = [], []
    for name, source, frame in frames:
        valid, invalid = normalize_one(frame, name, source)
        clean.append(valid)
        rejected.append(invalid)
    combined = pd.concat(clean, ignore_index=True)
    # Archive wins on identical observation keys; ties follow file name and CSV line.
    combined = combined.sort_values(["source_kind", "source_file", "source_row"], kind="stable")
    duplicate = combined.duplicated(KEY, keep="first")
    dropped = combined.loc[duplicate].copy()
    result = combined.loc[~duplicate].copy()

    def identity(row):
        fields = [row.satellite, row.instrument, format(float(row.latitude), ".17g"), format(float(row.longitude), ".17g"), row.acq_date, row.acq_time]
        return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()

    result.insert(0, "hotspot_id", result.apply(identity, axis=1) if len(result) else pd.Series(dtype="string"))
    result = result.sort_values(["acq_date", "acq_time", "latitude", "longitude", "hotspot_id"]).reset_index(drop=True)
    if result.hotspot_id.duplicated().any():
        raise ValueError("Hotspot ID collision")
    return result, pd.concat(rejected, ignore_index=True), dropped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    paths = sorted(args.raw_dir.glob("fire_*.csv"))
    if not paths:
        parser.error(f"No fire_*.csv files in {args.raw_dir}")
    frames = []
    report = {"files": {}, "schema_differences": []}
    for path in paths:
        source = "archive" if path.name.startswith("fire_archive_") else "nrt" if path.name.startswith("fire_nrt_") else None
        if source is None:
            raise ValueError(f"Unrecognized source filename: {path.name}")
        frame = read_csv(path)
        frames.append((path.name, source, frame))
        report["files"][path.name] = profile(frame)
        report["files"][path.name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name_a, source_a, a in frames:
        for name_b, source_b, b in frames:
            if source_a == "archive" and source_b == "nrt":
                report["schema_differences"].append({"archive": name_a, "nrt": name_b, "archive_only": sorted(set(a) - set(b)), "nrt_only": sorted(set(b) - set(a)), "shared": sorted(set(a) & set(b)), "note": "All columns are ingested as strings; numeric parsing is validated during normalization."})
    result, rejected, dropped = normalize(frames)
    common = sorted(set.intersection(*(set(f) for _, _, f in frames)))
    shared_rows = pd.concat([f[common] for _, _, f in frames], ignore_index=True)
    report["combined"] = {"input_rows": sum(len(f) for _, _, f in frames), "normalized_rows": len(result), "rejected_rows": len(rejected), "duplicate_observations_removed": len(dropped), "duplicates_on_shared_raw_columns_beyond_first": int(shared_rows.duplicated().sum()), "date_range": [result.acq_date.min(), result.acq_date.max()] if len(result) else [None, None], "missing_values": {c: int(result[c].isna().sum()) for c in result}, "columns": list(result.columns)}
    for directory in [args.processed_dir, args.output_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.processed_dir / "firms_normalized.csv", index=False)
    rejected.to_csv(args.output_dir / "rejected_rows.csv", index=False)
    dropped.to_csv(args.output_dir / "duplicate_observations.csv", index=False)
    serialized = json.dumps(report, indent=2, allow_nan=False)
    (args.output_dir / "profile_report.json").write_text(serialized + "\n", encoding="utf-8")
    (args.output_dir / "profile_report.md").write_text("# FIRMS profiling report\n\nComputed from local source CSVs. Dates without detections do not establish satellite observation coverage.\n\n```json\n" + serialized + "\n```\n", encoding="utf-8")
    for name, info in report["files"].items():
        print(f"{name}: {info['row_count']:,} rows; dates {info['date_range']}; exact duplicates {info['exact_duplicate_rows_beyond_first']}")
    print(json.dumps(report["combined"], indent=2))
    print(f"Full profiles: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
