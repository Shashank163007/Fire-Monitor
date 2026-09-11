"""Small synthetic fixtures test selection only; never used as scanned OSM data."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests

from src.scan_demo_regions import COLUMNS, fetch_cell, monthly_options, query_for, ranked, score, score_components, score_candidates, recommendation_candidates, select_candidates


def cell(lat, lon, count=100, active=10, both=True):
    return pd.DataFrame({"hotspot_id": [f"{lat}_{lon}_{i}" for i in range(count)], "latitude": lat + .25, "longitude": lon + .25, "acq_date": [(pd.Timestamp("2026-05-01") + pd.Timedelta(days=i % active)).strftime("%Y-%m-%d") for i in range(count)], "day_night": ["D" if i % 2 or not both else "N" for i in range(count)]})


def test_candidate_thresholds_full_period_and_limit():
    frame = pd.concat([cell(20, 70, 99), cell(21, 70, 100, 9), cell(22, 70, 100, 10), cell(23, 70, 200, 20)], ignore_index=True)
    result = select_candidates(frame)
    assert result.region_id.tolist() == ["cell_23_70", "cell_22_70"]
    assert select_candidates(frame, limit=1).region_id.tolist() == ["cell_23_70"]
    with pytest.raises(ValueError):
        select_candidates(frame, limit=7)


def test_day_night_presence_breaks_equal_activity_rank():
    result = select_candidates(pd.concat([cell(20, 70, both=False), cell(21, 70)], ignore_index=True))
    assert result.region_id.tolist() == ["cell_21_70", "cell_20_70"]


def test_nonoverlapping_exact_cells_and_deterministic_selection():
    frame = pd.concat([cell(20 + i, 70, count=100 + i) for i in range(8)], ignore_index=True)
    result = select_candidates(frame)
    assert len(result) == 6
    assert result.region_id.tolist() == select_candidates(frame.sample(frac=1, random_state=1)).region_id.tolist()
    assert (result.max_lat - result.min_lat).eq(1).all()
    assert (result.max_lon - result.min_lon).eq(1).all()
    for a in result.itertuples():
        for b in result.itertuples():
            if a.region_id != b.region_id:
                assert not (max(a.min_lat, b.min_lat) < min(a.max_lat, b.max_lat) and max(a.min_lon, b.min_lon) < min(a.max_lon, b.max_lon))


def test_integer_boundary_goes_to_north_east_cell():
    a, b = cell(20, 70), cell(21, 71)
    b["latitude"], b["longitude"] = 21.0, 71.0
    result = select_candidates(pd.concat([a, b], ignore_index=True))
    assert set(result.region_id) == {"cell_20_70", "cell_21_71"}


def test_suitability_weights_and_clipping():
    components = score_components(100, 1, 1000, 100, 1, 0, 100)
    assert components["positive_subtotal"] == 90
    assert components["normalized_positive_score"] == 100
    assert components["suitability_score"] == 100
    mined = score_components(100, 1, 1000, 100, 1, 100, 100)
    assert mined["mining_penalty"] == 30
    assert mined["suitability_score"] == 70
    assert components["suitability_score"] - mined["suitability_score"] == 30
    assert score(50, 1, 1, 50, 0, 50, 100) == round((55 / 90) * 100 - 15, 2)


@pytest.mark.parametrize("active,pct_i,pct_m", [(-10, -50, -100), (200, 150, 200), (0, 0, 100), (33, 43.123, 29.123), (np.inf, np.inf, np.inf)])
def test_all_component_inputs_clamped_and_scores_bounded(active, pct_i, pct_m):
    result = score_components(active, 1, 0, pct_i, 0, pct_m, 100)
    for key in ["active_date_score", "day_night_score", "industrial_proximity_score", "osm_availability_score", "mining_dominance_score"]:
        assert 0 <= result[key] <= 1
    assert 0 <= result["suitability_score"] <= 100
    assert result["suitability_score"] == round(result["suitability_score"], 2)
    with pytest.raises(ValueError, match="Missing component"):
        score_components(1, 1, 1, np.nan, 1, 0, 100)


@pytest.mark.parametrize("day,night,expected", [(1, 999, 1), (1, 0, .5), (0, 1, .5), (0, 0, 0)])
def test_day_night_component_uses_presence(day, night, expected):
    assert score_components(10, day, night, 0, 0, 0, 10)["day_night_score"] == expected


@pytest.mark.parametrize("status,features,expected", [("success", 1, 1), ("success", 0, .5), ("unavailable", 0, 0)])
def test_availability_component(status, features, expected):
    assert score_components(10, 1, 1, 0, features, 0, 10, status)["osm_availability_score"] == expected


def test_failed_queries_excluded_from_denominator_and_recommendation():
    rows = []
    for region, active, status in [("failed", 999, "unavailable"), ("ok", 50, "success"), ("other", 25, "success")]:
        row = {k: 1 for k in COLUMNS}
        row.update(region_id=region, active_dates=active, osm_query_status=status, suitability_score=100)
        rows.append(row)
    details = {r["region_id"]: {"months": [{"target_month": "2026-06"}]} for r in rows}
    result = score_candidates(rows, details)
    assert details["ok"]["max_active_dates_among_successful_candidates"] == 50
    assert details["ok"]["score_components"]["active_date_score"] == 1
    assert details["other"]["score_components"]["active_date_score"] == .5
    failed = result.loc[result.region_id.eq("failed")].iloc[0]
    assert pd.isna(failed.suitability_score) and pd.isna(failed.selection_rank)
    assert [r.region_id for r in recommendation_candidates(result, details)] == ["ok", "other"]
    # Defense in depth: injected/stale scores and ranks cannot recommend a failure.
    result.loc[result.region_id.eq("failed"), ["suitability_score", "selection_rank"]] = [100, 1]
    assert recommendation_candidates(result, details)[0].region_id == "ok"
    result["osm_query_status"] = "unavailable"
    assert recommendation_candidates(result, details) == []


def test_deterministic_tie_breaking_in_exact_priority_order():
    cases = [("top_score", 51, 0, 100, 1), ("top_industrial", 50, 81, 100, 1), ("low_mining", 50, 80, 1, 1), ("more_dates", 50, 80, 2, 11), ("a", 50, 80, 2, 10), ("z", 50, 80, 2, 10)]
    rows = []
    for region, value, pi, pm, active in cases:
        row = {k: 1 for k in COLUMNS}
        row.update(region_id=region, suitability_score=value, pct_near_industrial=pi, pct_near_mining=pm, active_dates=active, osm_query_status="success")
        rows.append(row)
    for seed in range(5):
        shuffled = pd.DataFrame(rows).sample(frac=1, random_state=seed).to_dict("records")
        assert ranked(shuffled).region_id.tolist() == [x[0] for x in cases]


def test_query_combines_contexts_without_expanding_bbox():
    query = query_for(SimpleNamespace(min_lat=21, max_lat=22, min_lon=72, max_lon=73))
    assert query.count("nwr") == 12
    assert query.count("(21,72,22,73)") == 12
    assert '["landuse"="quarry"]' in query and '["industrial"]' in query
    assert query.count("out body geom;") == 1


def test_unavailable_candidates_are_not_zero_scored_or_ranked():
    rows = []
    for region, value in [("a", np.nan), ("b", 0), ("c", 40)]:
        row = {k: 1 for k in COLUMNS}
        row.update(region_id=region, suitability_score=value, osm_query_status="unavailable" if np.isnan(value) else "success")
        rows.append(row)
    result = ranked(rows)
    assert result.region_id.tolist() == ["c", "b", "a"]
    assert result.selection_rank.iloc[:2].tolist() == [1, 2]
    assert pd.isna(result.selection_rank.iloc[2])


def test_network_failure_limited_retries_and_no_fake_response(tmp_path):
    class Session:
        def post(self, *args, **kwargs):
            raise requests.Timeout("fixture timeout")
    row = SimpleNamespace(region_id="test", min_lat=21, max_lat=22, min_lon=72, max_lon=73)
    detail, sleeps = {}, []
    assert fetch_cell(row, tmp_path, detail, Session(), sleeps.append) is None
    assert len(detail["requests"]) == 3 and sleeps == [2, 4]
    assert not list(tmp_path.iterdir())


def test_successful_empty_response_is_real_zero_context_and_cached(tmp_path):
    raw = b'{ "elements": [] }\n'
    class Response:
        content, status_code = raw, 200
        def raise_for_status(self):
            pass
    class Session:
        def post(self, *args, **kwargs):
            return Response()
    row = SimpleNamespace(region_id="test", min_lat=21, max_lat=22, min_lon=72, max_lon=73)
    detail = {}
    assert fetch_cell(row, tmp_path, detail, Session())["elements"] == []
    assert len(list(tmp_path.iterdir())) == 1
    assert next(tmp_path.iterdir()).read_bytes() == raw
    cached = {}
    fetch_cell(row, tmp_path, cached, Session())
    assert cached["requests"][0]["status"] == "cached"


def test_months_exclude_missing_previous_history_and_partial_september():
    frame = pd.concat([cell(21, 72) for _ in range(5)], ignore_index=True)
    for index, month in enumerate(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]):
        frame.loc[index * 100:(index + 1) * 100 - 1, "acq_date"] = [f"{month}-{i % 10 + 1:02}" for i in range(100)]
    frame["near_industrial"] = [bool(i % 2) for i in range(len(frame))]
    frame["near_mining"] = False
    options = monthly_options(frame, 25)
    assert {x["target_month"] for x in options} == {"2026-06", "2026-07", "2026-08"}
    assert all(x["history_month"] == str(pd.Period(x["target_month"], freq="M") - 1) for x in options)
    assert all(x["history_rows"] == 100 for x in options)
