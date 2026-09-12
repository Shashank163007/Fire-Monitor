"""Authenticated offline export and immutable snapshot startup validation."""
import copy
import json
from pathlib import Path
import socket
import pytest
import requests
from backend.config import SOURCE_HASHES
from backend.data_loader import DEMO_FILES, json_bytes, load_dataset, sha, validate_snapshot
from src import export_demo_data as export


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args,**kwargs): raise AssertionError('Export must remain offline')
    monkeypatch.setattr(requests.sessions.Session,'request',deny)
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'create_connection',deny)


@pytest.fixture(scope='module')
def snapshot():
    return export.build_export()


@pytest.fixture
def source_copy(tmp_path):
    for name in SOURCE_HASHES:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((export.ROOT/name).read_bytes())
    return tmp_path


def test_locked_hashes_counts_values_nulls_and_order(snapshot):
    data=validate_snapshot(snapshot)
    source=export.read_csv((export.ROOT/next(iter(SOURCE_HASHES))).read_bytes(),export.CLASSIFIED_FIELDS)
    assert len(data.hotspots)==674
    assert [h.hotspot_id for h in data.hotspots]==[r['hotspot_id'] for r in source]
    for h,r in zip(data.hotspots,source):
        assert h.predicted_class==r['predicted_class'] and h.risk_score==float(r['risk_score'])
        assert h.class_probability is None and h.acq_time==r['acq_time']
    assert data.manifest.class_counts.model_dump()==dict(industrial=308,wildfire=79,unknown=287)
    assert data.manifest.risk_band_counts.model_dump()==dict(critical=0,high=10,moderate=149,low=515)
    assert sum(g.hotspot_count for g in data.alert_groups)==10 and len(data.alert_groups)==6


@pytest.mark.parametrize('name',list(SOURCE_HASHES))
def test_missing_source_stops(source_copy,name):
    (source_copy/name).unlink()
    with pytest.raises(FileNotFoundError): export.build_export(source_copy)


@pytest.mark.parametrize('name',list(SOURCE_HASHES))
def test_changed_source_hash_stops(source_copy,name):
    path=source_copy/name;path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='SHA-256'): export.build_export(source_copy)


def test_repeat_export_bytes_manifest_no_self_reference_and_protected_sources(source_copy,snapshot):
    before={p:sha((source_copy/p).read_bytes()) for p in SOURCE_HASHES}
    first=export.export(source_copy); second=export.export(source_copy)
    assert first==second=={k:sha(v) for k,v in snapshot.items()}
    assert before=={p:sha((source_copy/p).read_bytes()) for p in SOURCE_HASHES}
    for name in DEMO_FILES:
        data=(source_copy/'backend/data'/name).read_bytes()
        assert data==snapshot[name] and data.endswith(b'\n')
        json.loads(data,parse_constant=lambda x:pytest.fail('Non-finite JSON'))
    m=json.loads(snapshot['demo_manifest.json'])
    assert {r['filename']:r['sha256'] for r in m['source_file_hashes']}==SOURCE_HASHES
    assert {r['filename'] for r in m['exported_file_hashes']}==set(DEMO_FILES[:2])
    assert 'generated_at' not in m and m['generated_at_policy']=='omitted_for_deterministic_export'
    assert m['dataset_mode']=='retrospective_demo' and m['classifier_operational'] is False


def test_module_relative_loading_and_deep_immutability(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    data=load_dataset()
    with pytest.raises(Exception): data.hotspots[0].risk_score=99
    with pytest.raises(Exception): data.manifest.class_counts.industrial=1
    with pytest.raises(TypeError): data.by_id['x']=data.hotspots[0]
    assert isinstance(data.hotspots,tuple) and isinstance(data.manifest.risk_distribution,tuple)


@pytest.mark.parametrize('issue',['missing','malformed','nan','duplicate_key','hash','self_hash','count','band_count','group','probability'])
def test_startup_rejects_invalid_snapshot(tmp_path,snapshot,issue):
    contents=dict(snapshot)
    if issue=='missing': contents.pop('demo_hotspots.json')
    elif issue=='malformed': contents['demo_hotspots.json']=b'not JSON'
    elif issue=='nan': contents['demo_hotspots.json']=b'[NaN]'
    elif issue=='duplicate_key': contents['demo_manifest.json']=b'{"a":1,"a":2}'
    else:
        m=json.loads(contents['demo_manifest.json'])
        if issue=='hash': m['exported_file_hashes'][0]['sha256']='0'*64
        elif issue=='self_hash': m['exported_file_hashes'].append(dict(filename='demo_manifest.json',sha256='0'*64))
        elif issue=='count': m['class_counts']['industrial']=307
        elif issue=='band_count': m['risk_band_counts']['critical']=1
        elif issue=='group':
            groups=json.loads(contents['demo_alert_groups.json']);groups[0]['hotspot_count']=2
            contents['demo_alert_groups.json']=json_bytes(groups)
            m['exported_file_hashes'][1]['sha256']=sha(contents['demo_alert_groups.json'])
        elif issue=='probability':
            rows=json.loads(contents['demo_hotspots.json']);rows[0]['class_probability']=.5
            contents['demo_hotspots.json']=json_bytes(rows)
            m['exported_file_hashes'][0]['sha256']=sha(contents['demo_hotspots.json'])
        contents['demo_manifest.json']=json_bytes(m)
    for name,data in contents.items(): (tmp_path/name).write_bytes(data)
    with pytest.raises(RuntimeError,match='startup validation'): load_dataset(tmp_path)
