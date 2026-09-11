import numpy as np
import pytest

from src.build_landcover_features import decision, readiness, weak_label


def row(i=2.0, m=2.0, land="Cropland", istatus="available", mstatus="available"):
    return {"distance_to_industrial_km": i, "nearest_mine_or_quarry_distance_km": m, "land_cover_class": land, "industrial_context_status": istatus, "mining_context_status": mstatus}


@pytest.mark.parametrize("land", ["Cropland", "Tree cover", "Permanent water bodies"])
def test_conflict_has_priority_over_all_landcover(land):
    result = weak_label(row(1, 1, land))
    assert result["weak_label"] == "conflict_excluded" and result["weak_label_conflict"] is True


@pytest.mark.parametrize("land", ["Cropland", "Tree cover", "Shrubland", "Built-up", "Unknown/Nodata"])
def test_industrial_rule_has_priority_and_exact_water_exclusion(land):
    assert weak_label(row(1, 1.01, land))["weak_label"] == "industrial_candidate"


def test_water_exclusion_and_natural_candidate_rules():
    assert weak_label(row(.2, 2, "Permanent water bodies"))["weak_label"] == "unknown"
    assert weak_label(row(2, 2, "Cropland"))["weak_label"] == "agricultural_burn_candidate"
    for land in ["Tree cover", "Shrubland"]:
        assert weak_label(row(2, 2, land))["weak_label"] == "wildfire_candidate"
    for land in ["Grassland", "Bare / sparse vegetation", "Unknown/Nodata"]:
        assert weak_label(row(2, 2, land))["weak_label"] == "unknown"
    assert weak_label(row(2, .1, "Cropland"))["weak_label"] == "unknown"


def test_unavailable_osm_never_becomes_far_context():
    for values in [row(np.nan, 2, istatus="unavailable"), row(2, np.nan, mstatus="unavailable"), row(.1, .1, istatus="unavailable"), row(np.nan, 2), row(2, np.nan)]:
        assert weak_label(values)["weak_label"] == "unknown_context_unavailable"
    assert weak_label(row(.1, np.nan, mstatus="no_mapped_objects"))["weak_label"] == "industrial_candidate"
    assert weak_label(row(2, np.nan, mstatus="no_mapped_objects"))["weak_label"] == "agricultural_burn_candidate"
    assert weak_label(row(np.nan, 2, istatus="no_mapped_objects"))["weak_label"] == "unknown"


def labels(i, a, w=0):
    return ["industrial_candidate"]*i + ["agricultural_burn_candidate"]*a + ["wildfire_candidate"]*w


@pytest.mark.parametrize("counts,ready", [((30,20,0), True), ((29,20,0), False), ((30,19,0), False), ((119,21,0), True), ((120,20,0), False), ((100,0,0), False), ((50,25,1), False), ((20,20,20), True), ((0,0,0), False)])
def test_exact_readiness_thresholds(counts, ready):
    result = readiness(labels(*counts), True)
    assert result["classifier_ready"] is ready
    if sum(counts):
        assert result["class_balance_ratio"] == max(counts)/min(c for c in counts if c)


def test_excluded_rows_not_counted_and_osm_failure_blocks_readiness():
    values = labels(30,20)+["conflict_excluded"]*100+["unknown"]*100+["unknown_context_unavailable"]*100
    result = readiness(values, True)
    assert result["usable_labelled_rows"] == 50 and result["usable_class_count"] == 2
    assert readiness(values, False)["classifier_ready"] is False


def test_no_recommendation_when_neither_qualifies():
    a = {"region_id": "A", **readiness(labels(100, 2), True)}
    b = {"region_id": "B", **readiness(labels(100, 0), True)}
    assert decision([a,b]) is None
    b.update(readiness(labels(30,20), True))
    assert decision([a,b]) == "B"
