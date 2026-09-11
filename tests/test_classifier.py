"""Stage 4 tests use local accepted observations or isolated algorithm fixtures."""
import copy
import io
import socket

import joblib
import numpy as np
import pandas as pd
import pytest
import requests

from src import train_classifier as tc


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError("Stage 4 must make zero network requests")
    monkeypatch.setattr(requests.sessions.Session,"request",forbidden)
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr(socket,"create_connection",forbidden)


@pytest.fixture(scope="module")
def inputs():
    return tc.read_inputs()


def ready(frame): return tc.er.readiness(frame)


def test_locked_input_schema_counts_and_target_mapping(inputs):
    audit,training=inputs
    tc.validate_inputs(audit,training,ready(training))
    assert len(audit)==674 and len(training)==387
    assert training.weak_label.map(tc.TARGET_MAP).value_counts().to_dict()=={"industrial":308,"wildfire":79}
    assert not audit.loc[~audit.weak_label.isin(tc.TARGET_MAP),"weak_label"].map(tc.TARGET_MAP).notna().any()


@pytest.mark.parametrize("issue",["count","label","id","schema","bounds","date","conflict","osm","landcover","readiness","audit_mismatch"])
def test_invalid_locked_input_stops_without_silent_dropping(inputs,issue):
    audit,training=[x.copy() for x in inputs]
    report=ready(training)
    if issue=="count": training=training.iloc[:-1]
    if issue=="label": training.loc[0,"weak_label"]="unknown"
    if issue=="id": training.loc[0,"hotspot_id"]=training.hotspot_id.iloc[1]
    if issue=="schema": training=training.drop(columns="bright_t31")
    if issue=="bounds": training.loc[0,"latitude"]=24
    if issue=="date": training.loc[0,"acq_date"]="2026-07-01"
    if issue=="conflict": training.loc[0,"weak_label_conflict"]=True
    if issue=="osm": training.loc[0,"industrial_query_success"]=False
    if issue=="landcover": training.loc[0,"land_cover_sample_status"]="nodata_or_unknown"
    if issue=="readiness": report["can_lock_region"]=False
    if issue=="audit_mismatch": training.loc[0,"frp"]=9999
    with pytest.raises(ValueError): tc.validate_inputs(audit,training,report)


def test_feature_allowlists_contextual_ablation_and_forbidden_fields(inputs):
    _,training=inputs
    for name in tc.MODEL_NAMES:
        X=tc.feature_frame(training,name)
        assert X.columns.tolist()==tc.feature_names(name)
        assert not set(X)&{"weak_label","target","predicted_class","class_probability","risk_score","risk_band","hotspot_id","latitude","longitude","core_osm_cell_id","weak_label_reason"}
        if name=="firms_only": assert set(X)==set(tc.NATIVE)
        else: pd.testing.assert_series_equal(X.distance_to_mining_km,training.nearest_mine_or_quarry_distance_km,check_names=False)
        pipeline=tc.make_pipeline(name)
        with pytest.raises(ValueError,match="allowlist"):
            pipeline.named_steps['clean'].fit(X.assign(target="industrial"))


def test_mixed_confidence_ordered_categories_numeric_preservation_and_missing():
    values=pd.Series([" L ","nominal","HIGH","n","low","h",33," 92.5 ",0,100,None,"","undocumented","120",-1,np.inf])
    normalized,unexpected=tc.normalize_confidence(values)
    assert normalized.iloc[:10].tolist()==[0,1,2,1,0,2,33,92.5,0,100]
    assert normalized.iloc[10:].isna().all() and unexpected==4


def test_preprocessing_fits_imputer_and_encoder_only_on_training_fold(inputs):
    X=tc.feature_frame(inputs[1].head(3),"contextual")
    X["frp"]=[1,9,np.nan]; X["day_night"]=[" D ","n",None]
    X["land_cover_class"]=[" Tree cover ","TREE COVER",None]
    preprocessing=tc.make_pipeline("contextual")[:-1]
    preprocessing.fit(X)
    transform=preprocessing.named_steps["preprocess"]
    index=list(transform.transformers_[0][2]).index("frp")
    assert transform.named_transformers_["numeric"].statistics_[index]==5
    categories=transform.named_transformers_["categorical"].named_steps["encoder"].categories_
    assert categories[0].tolist()==["d","n"] and categories[1].tolist()==["tree cover"]
    validation=X.copy(); validation["frp"]=10000; validation["land_cover_class"]="never seen in training"
    assert np.isfinite(preprocessing.transform(validation)).all()
    assert transform.named_transformers_["numeric"].statistics_[index]==5
    assert "never seen in training" not in categories[1]


def test_spatial_folds_exclusive_deterministic_and_both_classes(inputs):
    frame=inputs[1]; y=frame.weak_label.map(tc.TARGET_MAP).to_numpy()
    pairs=tc.near_pairs(frame)
    groups,folds,attempts=tc.choose_folds(frame,y,pairs)
    again,other,repeated=tc.choose_folds(frame,y,pairs)
    assert attempts==repeated and np.array_equal(groups,again)
    assert attempts[-1]["grid_degrees"]==.1 and len(folds)==5
    assert sorted(np.concatenate([v for t,v in folds]).tolist())==list(range(387))
    for (train,validation),(a,b) in zip(folds,other):
        assert np.array_equal(train,a) and np.array_equal(validation,b)
        assert not set(groups[train])&set(groups[validation])
        assert set(y[validation])==set(tc.CLASSES)
        validation=set(validation)
        assert not any((i in validation)!=(j in validation) for i,j in pairs)


def test_duplicate_and_near_observations_across_grid_edges_stay_together(inputs):
    frame=inputs[1].head(4).copy().reset_index(drop=True)
    frame["latitude"]=[21.5]*4; frame["longitude"]=[72.0999,72.1001,72.1001,73]
    frame["acq_date"]=["2026-06-01","2026-06-02","2026-06-02","2026-06-03"]
    frame["acq_time"]="0630"
    pairs=tc.near_pairs(frame)
    groups=tc.spatial_groups(frame,.1,pairs)
    assert groups[0]==groups[1]==groups[2] and groups[3]!=groups[0]
    report=tc.duplicate_audit(frame,pairs)
    assert report["duplicate_coordinate_rows_beyond_first"]==1
    assert report["exact_observation_duplicates_beyond_first"]==1
    assert report["rows_removed"]==0


def test_no_feasible_spatial_configuration_records_all_four_rejections(inputs):
    frame=inputs[1].copy(); frame["latitude"]=21.5; frame["longitude"]=72.5
    y=frame.weak_label.map(tc.TARGET_MAP).to_numpy()
    groups,folds,attempts=tc.choose_folds(frame,y,tc.near_pairs(frame))
    assert groups is None and folds is None
    assert [(r["grid_degrees"],r["fold_count"]) for r in attempts]==[(.1,5),(.1,3),(.05,5),(.05,3)]
    assert all(r["rejection_reasons"] for r in attempts)


def test_proxy_metric_calculations_and_auc_validity():
    result=tc.metrics_for(["industrial","industrial","wildfire","wildfire"],["industrial","wildfire","wildfire","wildfire"],[.1,.6,.9,.8])
    assert result["confusion_matrix"]==[[1,1],[0,2]]
    assert result["per_class"]["wildfire"]["recall"]==1
    assert result["macro_f1"]==pytest.approx((2/3+.8)/2)
    assert result["balanced_accuracy"]==.75 and result["roc_auc"]==1
    assert tc.metrics_for(["industrial","industrial"],["industrial","industrial"],[.1,.2])["roc_auc"] is None


def gate_report(macro=.75,recall=.60):
    return {"folds":[{"leakage_check":{"no_shared_spatial_groups":True},"validation_class_distribution":{"industrial":20,"wildfire":10}} for _ in range(3)],"mean_fold_metrics":{"macro_f1":macro,"wildfire_recall":recall}}


@pytest.mark.parametrize("macro,recall,passes",[(.75,.60,True),(.749,.9,False),(.9,.599,False),(.9,.9,True)])
def test_fixed_firms_only_go_no_go(macro,recall,passes):
    result=tc.go_no_go(gate_report(macro,recall))
    assert result["classifier_passes"] is passes
    assert result["operational_method"]==("firms_only_random_forest" if passes else "rule_based_weak_label_fallback")


def test_gate_rejects_group_overlap_missing_class_and_failures():
    for issue in ["groups","classes","folds","failure"]:
        report=gate_report(.9,.9)
        if issue=="groups": report['folds'][0]['leakage_check']['no_shared_spatial_groups']=False
        if issue=="classes": report['folds'][0]['validation_class_distribution']['wildfire']=0
        if issue=="folds": report['folds']=report['folds'][:2]
        assert not tc.go_no_go(report,failures=issue=="failure")["classifier_passes"]


@pytest.fixture(scope="module")
def fitted(inputs):
    frame=pd.concat([inputs[1].loc[inputs[1].weak_label.eq(label)].head(20) for label in tc.TARGET_MAP])
    y=frame.weak_label.map(tc.TARGET_MAP).to_numpy()
    result={}
    for name in tc.MODEL_NAMES:
        pipeline=tc.make_pipeline(name); pipeline.fit(tc.feature_frame(frame,name),y); result[name]=pipeline
    return frame,result


def test_parent_feature_importances_sum_and_sort(fitted):
    frame,models=fitted
    for name,model in models.items():
        values=tc.parent_importances(model)
        assert {r['feature'] for r in values}==set(tc.feature_names(name))
        assert sum(r['importance'] for r in values)==pytest.approx(1)
        assert values==sorted(values,key=lambda r:(-r['importance'],r['feature']))
    assert 'land_cover_class' not in tc.feature_names('firms_only')


def test_fixed_seed_raw_probability_and_portable_serialization_reproducible(fitted):
    frame,models=fitted
    X=tc.feature_frame(frame,"firms_only"); y=frame.weak_label.map(tc.TARGET_MAP).to_numpy()
    again=tc.make_pipeline('firms_only').fit(X,y)
    one=tc.deterministic_proba(models['firms_only'],X)
    assert np.array_equal(one,tc.deterministic_proba(again,X))
    assert models['firms_only'].named_steps['forest'].n_jobs==-1
    stream=io.BytesIO(); joblib.dump(models['firms_only'],stream); stream.seek(0)
    loaded=joblib.load(stream)
    assert np.array_equal(one,tc.deterministic_proba(loaded,X))


def test_674_row_contract_classifier_unknown_nulls_probability_range(inputs,fitted):
    audit,training=inputs
    output=tc.inference(audit,training,fitted[1]['firms_only'],{"classifier_passes":True})
    assert output.columns.tolist()==tc.CONTRACT and len(output)==674
    assert output.predicted_class.eq('unknown').sum()==287
    assert output.class_probability.notna().sum()==387
    assert output[["risk_score","risk_band"]].isna().all().all()
    assert output.acq_time.str.len().eq(4).all()
    invalid=output.copy(); invalid.loc[0,'class_probability']=1.1
    with pytest.raises(ValueError): tc.validate_output(invalid,set(training.hotspot_id),True)


def test_rule_fallback_preserves_candidates_and_never_fabricates_probability(inputs):
    audit,training=inputs
    output=tc.inference(audit,training,None,{"classifier_passes":False})
    assert output.predicted_class.value_counts().to_dict()=={"industrial":308,"unknown":287,"wildfire":79}
    assert output.class_probability.isna().all()
    assert tc.er.lc.csv_text(output)==tc.er.lc.csv_text(tc.inference(audit.sample(frac=1,random_state=1),training,None,{"classifier_passes":False}))


def test_atomic_outputs_leave_no_partial_files(tmp_path):
    contents={'outputs/a.json':b'{"ok":true}\n','data/a.csv':b'a\n1\n'}
    tc.atomic_publish(contents,tmp_path)
    for name,data in contents.items(): assert (tmp_path/name).read_bytes()==data
    assert not list(tmp_path.rglob('*.tmp'))
