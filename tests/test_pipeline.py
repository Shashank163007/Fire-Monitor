"""Synthetic unit fixtures only; never emitted as production data."""
import pandas as pd

from src.profile_firms import normalize, profile


def rows(**changes):
    row = dict(latitude="21.12345", longitude="82.54321", acq_date="2026-05-01", acq_time="630", satellite="N20", instrument="VIIRS", brightness="330", frp="5", confidence="n", daynight="D", version="2")
    row.update(changes)
    return pd.DataFrame([row], dtype="string")


def test_archive_precedence_nullable_type_and_stable_id():
    archive = rows(type="0")
    nrt = rows(version="2.0NRT", frp="6")
    other = rows(latitude="22.0")
    inputs = [("fire_nrt_b.csv", "nrt", pd.concat([nrt, other], ignore_index=True)), ("fire_archive_a.csv", "archive", archive)]
    clean, rejected, duplicates = normalize(inputs)
    assert len(clean) == 2 and rejected.empty and len(duplicates) == 1
    assert clean.acq_time.eq("0630").all()
    assert clean.loc[clean.source_kind.eq("archive"), "frp"].item() == 5
    assert clean.loc[clean.source_kind.eq("nrt"), "type"].isna().all()
    reverse, _, _ = normalize(list(reversed(inputs)))
    assert clean.hotspot_id.tolist() == reverse.hotspot_id.tolist()


def test_quarantine_invalid_values_without_discarding_valid_low_confidence():
    data = pd.concat([rows(latitude="91"), rows(acq_time="2460"), rows(frp="NaN-invalid"), rows(brightness="inf"), rows(confidence="l"), rows(frp=pd.NA, brightness=pd.NA)], ignore_index=True)
    clean, rejected, _ = normalize([("fire_nrt_a.csv", "nrt", data)])
    assert len(rejected) == 4
    # Final two rows have the same observation identity, so one survives deduplication.
    assert len(clean) == 1 and clean.confidence.item() == "l"
    assert rejected.rejection_reason.str.contains("invalid_acq_time").any()


def test_raw_duplicate_counts_and_missing_summary():
    frame = pd.concat([rows(), rows(), rows(frp=pd.NA)], ignore_index=True)
    result = profile(frame)
    assert result["exact_duplicate_rows_beyond_first"] == 1
    assert result["observation_key_duplicate_rows_beyond_first"] == 2
    assert result["missing_values"]["frp"]["count"] == 1


def test_header_only_input():
    empty = rows().iloc[:0]
    clean, rejected, duplicate = normalize([("fire_nrt_a.csv", "nrt", empty)])
    assert clean.empty and rejected.empty and duplicate.empty
    assert profile(empty)["date_range"] == [None, None]
