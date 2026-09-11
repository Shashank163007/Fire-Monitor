"""Stage 3.5 rules and real-cache integration; fixtures never become production data."""
from pathlib import Path
import hashlib
import io
import socket

import numpy as np
import pandas as pd
import pytest
import requests

from src import build_landcover_features as lc


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Stage 3.5 tests must not make network requests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def observations(dates):
    return pd.DataFrame([{**dict.fromkeys(lc.BASE), "hotspot_id": f"id{n:03d}", "latitude": 21.5, "longitude": 72.5, "acq_date": d, "acq_time": "0630", "frp": 5, "brightness": 300, "confidence": "n", "day_night": "D"} for n, d in enumerate(dates)])


def context_row(i=2, m=2, land=10, istatus="available", mstatus="available"):
    return {"distance_to_industrial_km": i, "nearest_mine_or_quarry_distance_km": m, "industrial_context_status": istatus, "mining_context_status": mstatus, "land_cover_code": land, "land_cover_class": lc.class_name(land), "land_cover_sample_status": "valid" if land in lc.CLASSES else "nodata_or_unknown"}


def eligible_fixture(industrial=30, wildfire=20):
    rows = []
    for label, count in [("industrial_candidate", industrial), ("wildfire_candidate", wildfire)]:
        for n in range(count):
            rows.append({**context_row(i=.5 if label == "industrial_candidate" else 2), "weak_label": label, "acq_date": "2026-06-15" if n % 2 == 0 else "2026-07-15", "persistence_history_complete": True})
    return pd.DataFrame(rows)


def test_exact_inclusive_boundary_and_june_first_starts_may_third():
    start, end = lc.persistence_window("2026-06-01")
    assert start == pd.Timestamp("2026-05-03") and end == pd.Timestamp("2026-06-01")
    assert len(pd.date_range(start, end)) == 30
    assert lc.persistence_window("2026-09-10")[0] == pd.Timestamp("2026-08-12")
    dates = pd.date_range("2026-05-01", "2026-06-02").strftime("%Y-%m-%d").tolist()
    target = lc.select_feature_targets(lc.REGIONS[1], observations(dates), "2026-06-01", "2026-06-01", "2026-05-01", True)
    assert target.persistence_count_30d.tolist() == [30]


def test_distinct_date_recurrence_and_no_future_detection_leakage():
    dates = ["2026-05-02", "2026-05-03", "2026-05-03", "2026-05-31", "2026-06-01", "2026-06-01", "2026-06-02"]
    frame = observations(dates)
    target = lc.select_feature_targets(lc.REGIONS[1], frame, "2026-06-01", "2026-06-01", "2026-05-01", True)
    assert target.persistence_count_30d.tolist() == [3, 3]
    # Spatially distinct cells do not inflate recurrence.
    frame.loc[frame.acq_date.eq("2026-05-31"), "longitude"] = 72.52
    target = lc.select_feature_targets(lc.REGIONS[1], frame, "2026-06-01", "2026-06-01", "2026-05-01", True)
    assert target.persistence_count_30d.tolist() == [2, 2]


@pytest.mark.parametrize("date,complete", [("2026-05-01", False), ("2026-05-29", False), ("2026-05-30", True), ("2026-06-01", True), ("2026-09-10", True), ("2026-09-11", False)])
def test_complete_history_uses_only_available_calendar_bounds(date, complete):
    assert lc.history_complete(date, "2026-05-01", "2026-09-10") is complete


def test_incomplete_rows_retained_and_calendar_coverage_not_daily_detections():
    frame = observations(["2026-05-01", "2026-05-29", "2026-05-30"])
    target = lc.select_feature_targets(lc.REGIONS[1], frame, "2026-05-29", "2026-05-30", "2026-05-01", True)
    assert target.persistence_history_complete.tolist() == [False, True]
    assert target.persistence_count_30d.tolist() == [2, 3]


def test_date_range_and_half_open_region_filtering():
    frame = observations(["2026-05-01", "2026-05-31", "2026-06-01", "2026-09-10", "2026-09-11", "2026-07-01", "2026-07-02"])
    frame.loc[5, "latitude"] = 22
    frame.loc[6, "longitude"] = 73
    target = lc.select_feature_targets(lc.REGIONS[1], frame, lc.EXTENDED_START, lc.EXTENDED_END, lc.AVAILABLE_START, True)
    assert target.acq_date.tolist() == ["2026-06-01", "2026-09-10"]
    with pytest.raises(ValueError, match="date range"):
        lc.select_feature_targets(lc.REGIONS[1], frame, "2026-07-01", "2026-06-01", "2026-05-01")


@pytest.mark.parametrize("i,m,land,label", [(1,1,80,"conflict_excluded"), (1,1,40,"conflict_excluded"), (1,2,40,"industrial_candidate"), (1,2,10,"industrial_candidate"), (1,2,80,"unknown"), (2,2,10,"wildfire_candidate"), (2,2,20,"wildfire_candidate"), (2,2,40,"cropland_hotspot_candidate"), (2,.5,40,"unknown"), (2,2,30,"unknown")])
def test_ordered_extended_weak_labels(i, m, land, label):
    result = lc.extended_weak_label(context_row(i, m, land))
    assert result["weak_label"] == label
    assert result["weak_label_conflict"] is (label == "conflict_excluded")
    assert result["weak_label"] not in {"agburn", "agricultural_burn_candidate", "flare"}


def test_failed_or_inconsistent_osm_never_means_no_objects():
    for row in [context_row(.1, np.nan, mstatus="unavailable"), context_row(np.nan, 2), context_row(.1,.1,istatus="unavailable"), context_row(-1,2), context_row(np.inf,2), context_row(2,np.nan,mstatus="unexpected")]:
        assert lc.extended_weak_label(row)["weak_label"] == "unknown_context_unavailable"
    assert lc.extended_weak_label(context_row(2,np.nan,mstatus="no_mapped_objects"))["weak_label"] == "wildfire_candidate"
    assert lc.extended_weak_label(context_row(np.nan,2,istatus="no_mapped_objects"))["weak_label"] == "unknown"


def test_only_two_classes_with_valid_context_and_history_can_train():
    frame = eligible_fixture()
    frame.loc[0, "persistence_history_complete"] = False
    frame.loc[1, ["land_cover_code", "land_cover_class", "land_cover_sample_status"]] = [0, lc.UNKNOWN, "nodata_or_unknown"]
    for label in ["cropland_hotspot_candidate", "conflict_excluded", "unknown", "unknown_context_unavailable", "agburn", "agricultural_burn_candidate"]:
        frame.loc[len(frame)] = {**context_row(2,2,40), "weak_label": label, "acq_date": "2026-06-15", "persistence_history_complete": True}
    pool = lc.eligible_context_mask(frame)
    train = pool & frame.persistence_history_complete
    assert pool.sum() == 49 and train.sum() == 48
    assert set(frame.loc[train, "weak_label"]) == set(lc.TWO_CLASS)
    assert lc.extended_readiness(frame)["eligible_training_rows"] == 48


@pytest.mark.parametrize("counts,ready", [((30,20),True), ((20,30),True), ((19,31),False), ((31,19),False), ((25,24),False), ((180,20),True), ((181,20),False), ((50,0),False)])
def test_fixed_class_count_total_and_balance_thresholds(counts, ready):
    assert lc.extended_readiness(eligible_fixture(*counts))["can_lock_region"] is ready


@pytest.mark.parametrize("incomplete,pass_history", [(10,True),(11,False)])
def test_eighty_percent_history_threshold_uses_pool_before_exclusion(incomplete, pass_history):
    frame = eligible_fixture()
    frame.loc[:incomplete-1, "persistence_history_complete"] = False
    result = lc.extended_readiness(frame)
    assert result["conditions"]["6_eligible_history_complete_at_least_80_percent"] is pass_history
    assert result["eligible_training_rows"] == 50-incomplete


@pytest.mark.parametrize("june,passes", [(40,True),(41,False)])
def test_class_month_concentration_exact_eighty_percent(june, passes):
    frame = eligible_fixture(50,50)
    for label in lc.TWO_CLASS:
        indices = frame.index[frame.weak_label.eq(label)]
        frame.loc[indices, "acq_date"] = ["2026-06-15"]*june + ["2026-07-15"]*(50-june)
    result = lc.extended_readiness(frame)
    assert result["conditions"]["7_each_class_month_concentration_at_most_80_percent"] is passes
    assert result["class_month_concentration"]["wildfire_candidate"]["maximum_month_percentage"] == 2*june


def test_monthly_reporting_includes_empty_months_and_partial_september():
    frame = eligible_fixture()
    frame.loc[0, "persistence_history_complete"] = False
    frame.loc[1, "acq_date"] = "2026-09-10"
    frame.loc[len(frame)] = {**context_row(2,2,40), "weak_label": "cropland_hotspot_candidate", "acq_date": "2026-08-15", "persistence_history_complete": True}
    monthly = lc.monthly_distribution(frame)
    assert monthly.period.tolist() == ["2026-06","2026-07","2026-08","2026-09"]
    assert monthly.period_end.iloc[-1] == "2026-09-10"
    assert monthly.total_hotspots.sum() == 51
    assert monthly.eligible_training_rows.sum() == 49
    assert monthly.cropland_hotspot_candidate.tolist() == [0,0,1,0]
    assert monthly.persistence_history_incomplete.sum() == 1


def test_missing_caches_do_not_attempt_network_or_create_raw_files(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setattr(lc, "RAW", tmp_path/"raw")
    payload, detail = lc.osm_context(lc.REGIONS[1], allow_network=False)
    assert payload is None and detail["status"] == "unavailable"
    with pytest.raises(FileNotFoundError):
        lc.cached_worldcover_tile(lc.REGIONS[1])
    assert list(tmp_path.iterdir()) == []


def test_failed_geometry_reconstruction_makes_every_row_context_unavailable(monkeypatch):
    def failed(*args, **kwargs):
        raise ValueError("Geometry reconstruction failed in isolated test")
    monkeypatch.setattr(lc, "convert", failed)
    tile = lc.cached_worldcover_tile(lc.REGIONS[1])
    audit, detail = lc.build_feature_audit(lc.REGIONS[1], observations(["2026-05-01","2026-06-01"]), tile, lc.EXTENDED_START, lc.EXTENDED_END, lc.AVAILABLE_START, extended=True)
    assert audit.weak_label.tolist() == ["unknown_context_unavailable"]
    assert not audit.training_eligible.any()
    assert lc.extended_readiness(audit)["conditions"]["5_all_eligible_context_valid"] is False
    assert "reconstruction_error" in detail["osm_geometry_audit"]


def test_real_cached_pipeline_zero_network_and_deterministic_output_bytes():
    # Integration reads the real local snapshots; it never writes project outputs.
    contents, result = lc.extended_artifacts()
    for relative, content in contents.items():
        assert content == (lc.ROOT/relative).read_bytes()
    audit = pd.read_csv(io.BytesIO(contents["data/processed/region_21_22_72_73_extended_audit.csv"]), dtype={"acq_time":"string"})
    assert len(audit) == 443 and audit.hotspot_id.is_unique
    assert audit.equals(lc.sorted_audit(audit))
    assert lc.csv_text(audit) == lc.csv_text(lc.sorted_audit(audit.sample(frac=1,random_state=9)))
    assert audit.training_eligible.equals(lc.eligible_context_mask(audit) & audit.persistence_history_complete)
    assert not audit.weak_label.isin(["agricultural_burn_candidate","agburn","flare"]).any()
    old = pd.read_csv(lc.ROOT/"data/processed/region_21_22_72_73_landcover_audit.csv", dtype={"acq_time":"string"})
    june = audit.loc[audit.acq_date.le("2026-06-30")].reset_index(drop=True)
    columns = [c for c in old if not c.startswith("weak_label")]
    pd.testing.assert_frame_equal(june[columns], old[columns])
    expected_labels = old.weak_label.replace({"agricultural_burn_candidate":"cropland_hotspot_candidate"})
    pd.testing.assert_series_equal(june.weak_label, expected_labels)
