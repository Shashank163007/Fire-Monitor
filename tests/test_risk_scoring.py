"""Stage 5 formulas and real-input integration; writes only isolated test directories."""
import ast
import copy
import json
import socket
from decimal import Decimal as D
from pathlib import Path

import pytest
import requests

from src import build_risk_scores as rs


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network access forbidden in Stage 5 tests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(scope="module")
def original_bytes():
    data = (rs.ROOT/rs.CLASSIFIED).read_bytes()
    rows, _ = rs.authenticate_input(data)
    base = [{**r, "risk_score": "", "risk_band": ""} for r in rows]
    result = rs.csv_bytes(base, rs.CONTRACT)
    assert rs.digest(result) == rs.STAGE4_HASH
    return result


@pytest.fixture
def rows(original_bytes):
    return rs.parse_csv(original_bytes)


@pytest.fixture
def isolated_root(tmp_path, original_bytes):
    for relative, data in {
        rs.CLASSIFIED: original_bytes,
        "outputs/classifier_metrics.json": (rs.ROOT/"outputs/classifier_metrics.json").read_bytes(),
        "docs/risk_scoring_specification.md": (rs.ROOT/"docs/risk_scoring_specification.md").read_bytes(),
        "requirements.txt": (rs.ROOT/"requirements.txt").read_bytes(),
        "docs/old_protected.txt": b"isolated preservation test fixture\n",
    }.items():
        p = tmp_path/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return tmp_path


def test_authenticate_original_and_preserved_contract(original_bytes):
    rows, mode = rs.authenticate_input(original_bytes)
    assert mode == "initial" and len(rows) == 674
    assert list(rows[0]) == rs.CONTRACT
    assert rs.digest(original_bytes) == rs.STAGE4_HASH


@pytest.mark.parametrize("issue", ["source", "order", "extra_newline", "score_only", "label_swap"])
def test_hash_mismatch_or_partial_scores_stop(original_bytes, rows, issue):
    if issue == "source":
        rows[0]["brightness"] = "999"
    elif issue == "order":
        rows[0], rows[1] = rows[1], rows[0]
    elif issue == "score_only":
        rows[0]["risk_score"] = "12.00"
    elif issue == "label_swap":
        rows[0]["predicted_class"], rows[1]["predicted_class"] = rows[1]["predicted_class"], rows[0]["predicted_class"]
    data = original_bytes+b"\n" if issue == "extra_newline" else rs.csv_bytes(rows, rs.CONTRACT)
    with pytest.raises(ValueError):
        rs.authenticate_input(data)


@pytest.mark.parametrize("issue", ["count", "class", "duplicate", "null_id", "probability", "risk", "band", "schema", "latitude", "longitude", "date", "time"])
def test_critical_locked_validation(rows, issue):
    if issue == "count": rows.pop()
    elif issue == "class": rows[0]["predicted_class"] = "wildfire"
    elif issue == "duplicate": rows[0]["hotspot_id"] = rows[1]["hotspot_id"]
    elif issue == "null_id": rows[0]["hotspot_id"] = ""
    elif issue == "probability": rows[0]["class_probability"] = "0.5"
    elif issue == "risk": rows[0]["risk_score"] = "1"
    elif issue == "band": rows[0]["risk_band"] = "low"
    elif issue == "schema": rows[0].pop("confidence")
    elif issue == "latitude": rows[0]["latitude"] = "24"
    elif issue == "longitude": rows[0]["longitude"] = "75"
    elif issue == "date": rows[0]["acq_date"] = "2026-07-01"
    elif issue == "time": rows[0]["acq_time"] = "835"
    with pytest.raises(ValueError): rs.validate_rows(rows)


@pytest.mark.parametrize("value", ["", "no", "nan", "inf", "-1"])
def test_frp_invalid_stops(rows, value):
    rows[0]["frp"] = value
    with pytest.raises(ValueError, match="frp"): rs.validate_rows(rows)


@pytest.mark.parametrize("value", ["", "no", "NaN", "Infinity", "0", "31", "1.5"])
def test_persistence_invalid_stops(rows, value):
    rows[0]["persistence_count_30d"] = value
    with pytest.raises(ValueError, match="persistence"): rs.validate_rows(rows)


@pytest.mark.parametrize("frp,points", [(0,0),(5,0),(20,10),(50,25),(100,35),(200,40),(10000,40)])
def test_exact_frp_breakpoints(frp, points):
    assert rs.frp_points(frp) == points


def test_frp_continuous_monotone():
    values = [rs.frp_points(D(i)/10) for i in range(3001)]
    assert values == sorted(values) and all(0 <= x <= 40 for x in values)
    for breakpoint in [5,20,50,100,200]:
        left, right = rs.frp_points(D(breakpoint)-D('.000001')), rs.frp_points(D(breakpoint)+D('.000001'))
        assert 0 <= right-left < D('.00001')


def test_persistence_endpoints_and_monotonicity():
    values = [rs.persistence_points(i) for i in range(1,31)]
    assert values[0] == 0 and values[-1] == 30
    assert all(b > a for a,b in zip(values, values[1:]))
    assert rs.persistence_points(15) == D(14)/29*30


@pytest.mark.parametrize("raw,canonical,points,status", [
    (" L ","low",5,"valid"),("LOW","low",5,"valid"),("n","nominal",12,"valid"),
    (" Nominal ","nominal",12,"valid"),("h","high",20,"valid"),("HIGH","high",20,"valid"),
    (0,"0",0,"valid"),(100,"100",20,"valid"),(" 62.5 ","62.5",D('12.5'),"valid"),
    (None,"unknown",0,"missing"),(" ","unknown",0,"missing"),("other","unknown",0,"unexpected"),
    (101,"unknown",0,"unexpected"),(-1,"unknown",0,"unexpected"),("NaN","unknown",0,"unexpected"),
])
def test_confidence_normalization(raw, canonical, points, status):
    assert rs.confidence_value(raw) == (canonical, D(points), status)


@pytest.mark.parametrize("raw,canonical,points,status", [
    (" N ","night",10,"valid"),("NIGHT","night",10,"valid"),
    ("d","day",0,"valid"),(" Day ","day",0,"valid"),
    (None,"unknown",0,"missing"),(" ","unknown",0,"missing"),("x","unknown",0,"unexpected"),
])
def test_day_night_normalization(raw, canonical, points, status):
    assert rs.day_night_value(raw) == (canonical, D(points), status)


def test_component_bounds_final_bounds_and_exact_score():
    for f in [0,5,20,50,100,200,10000]:
        for p in [1,15,30]:
            for c in [None,'l','n','h',0,100,'unknown']:
                for dn in ['D','N',None]:
                    score = rs.score_inputs(f,p,c,dn)
                    assert all(0 <= score[k] <= limit for k,limit in zip(rs.COMPONENTS,[40,30,20,10]))
                    assert 0 <= score['risk_score'] <= 100
    assert rs.score_inputs(200,30,'h','N')['risk_score'] == 100
    assert rs.score_inputs(5,1,None,'D')['risk_score'] == 0
    assert rs.score_inputs(20,30,'n','N')['risk_score'] == 62
    assert rs.score_inputs(50,15,'l','N')['risk_score'] == D('54.48')


@pytest.mark.parametrize("score,band", [('34.99','low'),('35.00','moderate'),('54.99','moderate'),('55.00','high'),('74.99','high'),('75.00','critical')])
def test_exact_band_boundaries(score, band):
    assert rs.band(score) == band


def test_class_invariance_and_context_exclusion(rows):
    original, _ = rs.build_tables(rows)
    changed = copy.deepcopy(rows)
    for r in changed:
        r['predicted_class'] = {'industrial':'unknown','unknown':'wildfire','wildfire':'industrial'}[r['predicted_class']]
        for key in ['distance_to_industrial_km','land_cover_class','latitude','longitude','brightness','class_probability']:
            r[key] = '' if key == 'class_probability' else 'irrelevant'
    # Test the scoring boundary directly; coordinates are separately required for summaries.
    for before, after in zip(rows, changed):
        assert rs.score_inputs(*(before[c] for c in ['frp','persistence_count_30d','confidence','day_night'])) == rs.score_inputs(*(after[c] for c in ['frp','persistence_count_30d','confidence','day_night']))
    unknown = [r for r in original[0] if r['predicted_class']=='unknown']
    assert len(unknown)==287 and all(0 <= D(r['risk_score']) <= 100 for r in unknown)


def test_primary_driver_exact_ties_and_safe_explanations(rows):
    assert rs.primary_driver([10,10,10,10]) == 'thermal_intensity'
    assert rs.primary_driver([0,10,10,10]) == 'persistence'
    assert rs.primary_driver([0,0,10,10]) == 'observation_confidence'
    assert rs.primary_driver([0,0,0,10]) == 'night_observation'
    assert rs.primary_driver([0,0,0,0]) == 'thermal_intensity'
    tables,_ = rs.build_tables(rows)
    forbidden = ['confirmed industrial fire','confirmed wildfire','verified emergency','dispatch immediately','certain cause','probability of fire','predicted damage']
    for row in tables[1]:
        assert 'review priority' in row['explanation']
        assert f"Rule-based context category: {row['predicted_class']}." in row['explanation']
        assert not any(term in row['explanation'].lower() for term in forbidden)


def test_invalid_confidence_and_day_night_are_counted(rows):
    rows[0]['confidence']='surprise'; rows[1]['confidence']=''
    rows[0]['day_night']='surprise'; rows[1]['day_night']=''
    tables,validation=rs.build_tables(rows)
    assert all(validation['invalid_or_missing'][key]==1 for key in ['confidence_missing','confidence_unexpected','day_night_missing','day_night_unexpected'])
    assert tables[1][0]['confidence_points']=='0' and tables[1][0]['night_points']=='0'


def test_outputs_order_contract_filter_and_distribution_reconcile(rows):
    tables,_=rs.build_tables(rows)
    scored,audit,alerts,summary,dist=tables
    assert len(scored)==674 and len(audit)==674 and len(dist)==20
    assert [r['hotspot_id'] for r in scored]==[r['hotspot_id'] for r in rows]
    for source,out in zip(rows,scored):
        assert list(out)==rs.CONTRACT
        assert all(source[k]==out[k] for k in rs.CONTRACT[:-2])
        assert out['class_probability']==''
    assert all(r['risk_band'] in ['high','critical'] and r['alert_id']=='ALT-'+r['hotspot_id'] for r in alerts)
    assert alerts==sorted(alerts,key=rs.alert_key)
    assert sum(r['hotspot_count'] for r in summary)==len(alerts)
    assert sum(r['hotspot_count'] for r in dist if r['predicted_class'] in rs.CLASSES and r['risk_band'] in rs.BANDS)==674
    assert dist[-1]['hotspot_count']==674
    assert [(r['predicted_class'],r['risk_band']) for r in dist]==[(c,b) for c in rs.CLASSES+['overall'] for b in rs.BANDS+['all']]
    assert all(r['minimum_score']=='' for r in dist if not r['hotspot_count'])


def test_grid_edges_dates_representatives_and_severity():
    assert rs.grid_index('21.05')==421 and rs.grid_index('21.049999999')==420
    assert rs.grid_index('-0.0001')==-1 and rs.grid_index('72.10')==1442
    base=dict(latitude='21.05',longitude='72.10',acq_date='2026-06-01',acq_time='0835',predicted_class='unknown',frp='20',persistence_count_30d='30',risk_score='75.00',risk_band='critical')
    a=dict(base,hotspot_id='z'); b=dict(base,hotspot_id='a'); c=dict(base,hotspot_id='c',acq_date='2026-06-02')
    result=rs.daily_summary([a,c,b])
    assert len(result)==2 and result[0]['hotspot_count']==2
    assert result[0]['alert_group_id']=='20260601-421-1442'
    assert result[0]['grid_min_latitude']=='21.05' and result[0]['grid_max_latitude']=='21.10'
    assert result[0]['representative_hotspot_id']=='a' and result[0]['highest_risk_band']=='critical'
    assert result[0]['mean_frp']=='20.00' and result[0]['unknown_count']==2
    variants=[dict(base,hotspot_id='p',risk_score='76'),dict(base,hotspot_id='q',persistence_count_30d='29'),dict(base,hotspot_id='r',frp='21'),dict(base,hotspot_id='s',acq_time='0834')]
    assert [r['hotspot_id'] for r in sorted([a,b,*variants],key=rs.alert_key)]==['p','r','s','a','z','q']
    assert rs.daily_summary([])==[]


def test_operational_or_confidence_conflict_stops():
    original=json.loads((rs.ROOT/'outputs/classifier_metrics.json').read_bytes())
    rs.validate_operational_state(original)
    for issue in ['decision','counts','confidence']:
        changed=copy.deepcopy(original)
        if issue=='decision': changed['decision']['classifier_passes']=True
        if issue=='counts': changed['final_class_counts']['industrial']=1
        if issue=='confidence': changed['confidence']['categorical_ordinal_mapping']['l/low']=5
        with pytest.raises(ValueError): rs.validate_operational_state(changed)


def test_real_input_two_runs_hashes_offline_no_models_and_preservation(isolated_root):
    before=rs.protected_hashes(isolated_root)
    one=rs.run_pipeline(isolated_root)
    two=rs.run_pipeline(isolated_root)
    assert one['input_mode']=='initial' and two['input_mode']=='verified_cached'
    assert one['output_sha256']==two['output_sha256']
    assert one['network_attempts']==two['network_attempts']==0
    assert one['model_import_attempts']==two['model_import_attempts']==0
    assert before==rs.protected_hashes(isolated_root)
    assert rs.authenticate_input((isolated_root/rs.CLASSIFIED).read_bytes())[1]=='verified_cached'
    assert not list(isolated_root.rglob('*.tmp'))
    # The module has no classifier/model/network library import and no model invocation.
    tree=ast.parse((rs.ROOT/'src/build_risk_scores.py').read_text())
    imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert not any(x.startswith(('sklearn','joblib','requests','src.train_classifier','pickle')) for x in imports)


@pytest.mark.parametrize('field,value',[('risk_score','99.99'),('risk_band','critical'),('risk_score','')])
def test_cached_score_tampering_stops_without_writes(isolated_root,field,value):
    rs.run_pipeline(isolated_root)
    path=isolated_root/rs.CLASSIFIED
    rows=rs.parse_csv(path.read_bytes()); rows[0][field]=value
    data=rs.csv_bytes(rows,rs.CONTRACT); path.write_bytes(data)
    with pytest.raises(ValueError): rs.run_pipeline(isolated_root)
    assert path.read_bytes()==data


def test_execution_guard_blocks_network_and_model_imports():
    with pytest.raises(RuntimeError,match='network'):
        with rs.execution_guard(): socket.create_connection(('example.invalid',80))
    with pytest.raises(RuntimeError,match='model'):
        with rs.execution_guard(): __import__('joblib')


def test_protected_integrity_and_atomic_failure(isolated_root,monkeypatch):
    before=rs.protected_hashes(isolated_root)
    path=isolated_root/'docs/old_protected.txt'; path.write_text('changed')
    with pytest.raises(RuntimeError,match='integrity'): rs.assert_protected(before,isolated_root)
    with pytest.raises(ValueError,match='allowlist'): rs.atomic_publish({'outputs/classifier_metrics.json':b'bad'},isolated_root)
    original=(isolated_root/rs.CLASSIFIED).read_bytes()
    def fail(*args): raise OSError('isolated replacement failure')
    monkeypatch.setattr(rs.os,'replace',fail)
    with pytest.raises(OSError): rs.atomic_publish({rs.CLASSIFIED:b'not published'},isolated_root)
    assert (isolated_root/rs.CLASSIFIED).read_bytes()==original
    assert not list(isolated_root.rglob('*.tmp'))
