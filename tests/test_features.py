"""Synthetic fixtures validate algorithms; never used as real OSM context."""
import geopandas as gpd
import pandas as pd
import pytest
import requests
from shapely.geometry import Point, Polygon

from src.build_features import (GEOD, convert, element_geometry, fetch, grid_id,
                                nearest_asset, persistence, queries)


def test_distinct_dates_inclusive_window_and_no_future_leakage():
    history = pd.DataFrame({"grid_cell_id": ["a"] * 6 + ["b"], "acq_date": ["2026-05-02", "2026-05-03", "2026-05-03", "2026-05-31", "2026-06-01", "2026-06-02", "2026-05-31"]})
    targets = pd.DataFrame({"grid_cell_id": ["a", "a", "b"], "acq_date": ["2026-06-01", "2026-06-02", "2026-06-01"]})
    # June 1 starts May 3; June 2 starts May 4. Same-day detections count once.
    assert persistence(history, targets).tolist() == [3, 3, 1]


def test_thirty_distinct_days_and_same_day_duplicates():
    dates = pd.date_range("2026-05-01", "2026-06-30").strftime("%Y-%m-%d").tolist()
    history = pd.DataFrame({"grid_cell_id": ["a"] * len(dates) * 2, "acq_date": dates * 2})
    target = pd.DataFrame({"grid_cell_id": ["a", "a"], "acq_date": ["2026-06-01", "2026-06-30"]})
    assert persistence(history, target).tolist() == [30, 30]


def test_grid_edges_and_negative_coordinates():
    assert grid_id(23.01, 86.01) == "g001_2301_8601"
    assert grid_id(23.009999, 86.009999) == "g001_2300_8600"
    assert grid_id(-0.001, -0.001) == "g001_-1_-1"


def assets(geometries):
    return gpd.GeoDataFrame({"osm_id": [f"test/{i}" for i in range(len(geometries))]}, geometry=geometries, crs=4326)


def test_point_distance_matches_wgs84_geodesic_and_selects_nearest():
    lon, lat, _ = GEOD.fwd(86.5, 23.5, 90, 1000)
    nearest, km = nearest_asset(86.5, 23.5, assets([Point(86.8, 23.5), Point(lon, lat)]))
    assert nearest.osm_id == "test/1"
    assert km == pytest.approx(1.0, abs=1e-8)


def test_polygon_distance_is_to_footprint_and_respects_hole():
    polygon = Polygon([(86.4, 23.4), (86.6, 23.4), (86.6, 23.6), (86.4, 23.6)], holes=[[(86.49, 23.49), (86.51, 23.49), (86.51, 23.51), (86.49, 23.51)]])
    assert nearest_asset(86.45, 23.45, assets([polygon]))[1] == 0
    assert nearest_asset(86.5, 23.5, assets([polygon]))[1] > 1
    # Meridian boundary: a point 1 km east of its midpoint has a 1 km minimum.
    lon, lat, _ = GEOD.fwd(86.6, 23.5, 90, 1000)
    assert nearest_asset(lon, lat, assets([polygon]))[1] == pytest.approx(1, abs=1e-5)


def test_empty_assets_are_missing_not_zero():
    row, distance = nearest_asset(86.5, 23.5, assets([]))
    assert row is None and pd.isna(distance)


def test_mining_tags_never_enter_industrial_pool():
    payload = {"elements": [{"type": "node", "id": 1, "lat": 23.5, "lon": 86.5, "tags": {"industrial": "mine", "landuse": "industrial"}}, {"type": "node", "id": 2, "lat": 23.6, "lon": 86.6, "tags": {"power": "plant", "name": "Test fixture"}}]}
    industrial, mining = convert({"industrial": payload, "mining": {"elements": []}}, {})
    assert industrial.osm_id.tolist() == ["node/2"]
    assert mining.osm_id.tolist() == ["node/1"]


def test_relation_split_outer_and_inner_ring():
    def member(coords, role):
        return {"type": "way", "role": role, "geometry": [{"lon": x, "lat": y} for x, y in coords]}
    element = {"type": "relation", "tags": {"type": "multipolygon"}, "members": [member([(86, 23), (87, 23), (87, 24)], "outer"), member([(87, 24), (86, 24), (86, 23)], "outer"), member([(86.4, 23.4), (86.6, 23.4), (86.6, 23.6), (86.4, 23.6), (86.4, 23.4)], "inner")]}
    geom = element_geometry(element)
    assert geom.is_valid and len(geom.interiors) == 1
    assert not geom.covers(Point(86.5, 23.5))


def test_industrial_object_inside_mine_is_excluded():
    mine = {"type": "way", "id": 5, "tags": {"landuse": "quarry"}, "geometry": [{"lon": x, "lat": y} for x, y in [(86, 23), (87, 23), (87, 24), (86, 24), (86, 23)]]}
    plant = {"type": "node", "id": 6, "lat": 23.5, "lon": 86.5, "tags": {"building": "industrial"}}
    state = {}
    industrial, mining = convert({"industrial": {"elements": [plant]}, "mining": {"elements": [mine]}}, state)
    assert industrial.empty and len(mining) == 1
    assert state["mining_overlap_excluded"] == ["node/6"]


def test_rate_limit_then_partial_response_cannot_be_accepted(tmp_path):
    class Response:
        def __init__(self, status, content):
            self.status_code, self.content = status, content
        def raise_for_status(self):
            if self.status_code != 200:
                raise requests.HTTPError("HTTP 429")
    class Session:
        def __init__(self):
            self.responses = iter([Response(429, b'limited'), Response(200, b'{"elements":[],"remark":"runtime timeout"}'), Response(200, b'{"elements":[]}')])
        def post(self, *args, **kwargs):
            return next(self.responses)
    state, waits = {"requests": []}, []
    fetch("mining", queries()["mining"], tmp_path, state, session=Session(), sleep=waits.append)
    assert [x["status"] for x in state["requests"]] == ["failed", "failed", "success"]
    assert len(list(tmp_path.glob('*attempt*.json'))) == 3
    assert waits == [2, 4]


def test_retry_exhaustion_is_explicit_and_logged(tmp_path):
    class Session:
        def post(self, *args, **kwargs):
            raise requests.Timeout("test timeout")
    state, waits = {"requests": []}, []
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        fetch("industrial", queries()["industrial"], tmp_path, state, session=Session(), sleep=waits.append)
    assert len(state["requests"]) == 3 and waits == [2, 4]


def test_raw_response_preserved_and_cache_validated(tmp_path):
    raw = b'{ "elements": [] , "osm3s": {} }\n'
    class Response:
        content, status_code = raw, 200
        def raise_for_status(self):
            pass
    class Session:
        def post(self, *args, **kwargs):
            return Response()
    state = {"requests": []}
    fetch("mining", queries()["mining"], tmp_path, state, session=Session())
    entry = state["requests"][0]
    assert (tmp_path / entry["response_file"]).read_bytes() == raw
    fetch("mining", queries()["mining"], tmp_path, state, session=Session())
    assert state["requests"][-1]["status"] == "cache_hit"
    (tmp_path / entry["response_file"]).write_bytes(b'{}')
    with pytest.raises(ValueError, match="hash mismatch"):
        fetch("mining", queries()["mining"], tmp_path, state, session=Session())
