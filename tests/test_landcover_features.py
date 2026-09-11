import numpy as np
import pandas as pd
import pytest
import rasterio
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from src.build_landcover_features import CLASSES, UNKNOWN, REGIONS, class_name, csv_text, footprint_summary, required_tiles, sample_landcover, sorted_audit
from src import build_landcover_features as lc


def test_official_worldcover_mapping():
    assert CLASSES == {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare / sparse vegetation", 70: "Snow and ice", 80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"}
    assert class_name(0) == class_name(None) == class_name(255) == UNKNOWN


def test_official_grid_selects_only_covering_tiles():
    grid = {"features": [{"properties": {"ll_tile": name}, "geometry": mapping(box(*bounds))} for name, bounds in [("N15E075", (75, 15, 78, 18)), ("N21E072", (72, 21, 75, 24)), ("N18E072", (72, 18, 75, 21))]]}
    selected = required_tiles(grid)
    assert list(selected) == ["N15E075", "N21E072"]
    assert selected["N15E075"]["regions"] == [REGIONS[0].region_id]
    grid["features"][1]["geometry"] = mapping(box(72, 21, 75, 24).difference(box(72.5, 21.5, 72.6, 21.6)))
    assert list(required_tiles(grid)) == ["N15E075", "N21E072"]
    with pytest.raises(RuntimeError):
        required_tiles({"features": []})


def test_footprint_proportions_ignore_nodata_and_preserve_other_classes():
    values = np.ma.array([[10, 10, 20, 40], [50, 60, 80, 30], [0, 255, 95, 90]], mask=False)
    result = footprint_summary(values)
    assert result["footprint_valid_pixel_count"] == 10
    assert result["footprint_total_pixel_count"] == 12
    assert result["footprint_dominant_class"] == "Tree cover"
    assert result["footprint_dominant_proportion"] == .2
    assert result["footprint_tree_cover_proportion"] == .2
    for name in ["shrubland", "cropland", "built_up", "bare_sparse_vegetation", "water"]:
        assert result[f"footprint_{name}_proportion"] == .1
    empty = footprint_summary(np.zeros((2, 2), dtype="uint8"))
    assert empty["footprint_valid_pixel_count"] == 0
    assert empty["footprint_dominant_class"] == UNKNOWN
    assert empty["footprint_water_proportion"] is None
    assert footprint_summary(np.array([50, 40]))["footprint_dominant_class"] == "Cropland"


def test_coordinate_pixel_nodata_footprint_and_boundary_handling():
    # Fixtures are in-memory algorithm tests, never external-data replacements.
    array = np.full((100, 100), 10, dtype="uint8")
    array[50, 50] = 40
    array[5, 5] = 0
    transform = from_origin(76.0, 15.02, 1/12000, 1/12000)
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", width=100, height=100, count=1, dtype="uint8", crs="EPSG:4326", transform=transform, nodata=0) as dst:
            dst.write(array, 1)
        with mem.open() as src:
            lon, lat = src.xy(50, 50)
            result = sample_landcover(src, lon, lat)
            assert result["land_cover_code"] == 40
            assert result["land_cover_class"] == "Cropland"
            assert result["footprint_dominant_class"] == "Tree cover"
            assert result["footprint_dominant_proportion"] > .99
            assert 1600 <= result["footprint_valid_pixel_count"] <= 2200
            assert result["footprint_clipped_at_raster_edge"] is False
            nodata = sample_landcover(src, *src.xy(5, 5))
            assert nodata["land_cover_code"] == 0 and nodata["land_cover_class"] == UNKNOWN
            edge = sample_landcover(src, *src.xy(0, 0))
            assert edge["footprint_clipped_at_raster_edge"] is True
            assert edge["footprint_valid_pixel_count"] < edge["footprint_total_pixel_count"]
            assert sample_landcover(src, src.bounds.right, lat)["land_cover_sample_status"] == "outside_raster"
            assert sample_landcover(src, lon, src.bounds.bottom)["land_cover_sample_status"] == "outside_raster"
            assert sample_landcover(src, src.bounds.left, src.bounds.top)["land_cover_sample_status"] == "valid"


def test_deterministic_sort_and_csv_without_timestamp():
    rows = pd.DataFrame({"acq_date": ["2026-06-02", "2026-06-01", "2026-06-01", "2026-06-01"], "acq_time": ["0630"]*4, "latitude": [15.2, 15.1, 15.1, 15.1], "longitude": [76.2, 76.3, 76.2, 76.2], "hotspot_id": ["a", "b", "d", "c"], "distance": [1.123456, np.nan, 0, 2]})
    expected = sorted_audit(rows)
    assert expected.hotspot_id.tolist() == ["c", "d", "b", "a"]
    assert csv_text(expected) == csv_text(sorted_audit(rows.sample(frac=1, random_state=42)))
    assert "0630" in csv_text(expected)


def test_valid_cache_avoids_network_and_detects_changed_bytes(tmp_path, monkeypatch):
    path = tmp_path / "official_grid.geojson"
    path.write_text('{"type":"FeatureCollection","features":[1]}', encoding="utf-8")
    expected = {"sha256": lc.checksum(path), "file_size": path.stat().st_size}
    def forbid_network(*args, **kwargs):
        raise AssertionError("A valid cache must not make any HTTP request")
    monkeypatch.setattr(lc.requests, "get", forbid_network)
    assert lc.download("https://example.invalid", path, lc.validate_grid, expected)["features"] == [1]
    path.write_text('{"type":"FeatureCollection","features":[2]}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="integrity mismatch"):
        lc.download("https://example.invalid", path, lc.validate_grid, expected)


def test_official_download_failure_is_bounded_and_creates_no_dummy(tmp_path, monkeypatch):
    calls, delays = [], []
    def unavailable(*args, **kwargs):
        calls.append(args)
        raise requests.Timeout("offline test")
    monkeypatch.setattr(lc.requests, "get", unavailable)
    monkeypatch.setattr(lc.time, "sleep", delays.append)
    path = tmp_path / "map.tif"
    with pytest.raises(RuntimeError, match="No dummy replacement"):
        lc.download("https://example.invalid", path, lambda p: None)
    assert len(calls) == 3 and delays == [2, 4]
    assert not path.exists()


@pytest.mark.parametrize("crs,bands,error", [("EPSG:3857", 1, "EPSG:4326"), ("EPSG:4326", 2, "single uint8"), ("EPSG:4326", 1, "resolution/dimensions")])
def test_tile_validation_rejects_wrong_crs_band_and_resolution(tmp_path, crs, bands, error):
    path = tmp_path / "test.tif"
    with rasterio.open(path, "w", driver="GTiff", width=10, height=10, count=bands, dtype="uint8", crs=crs, transform=from_origin(75, 18, .3, .3)) as dst:
        dst.write(np.ones((bands, 10, 10), dtype="uint8"))
    with pytest.raises(ValueError, match=error):
        lc.validate_tile(path, [75, 15, 78, 18])
