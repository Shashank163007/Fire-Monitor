"""In-process HTTP contract tests; no HTTP client opens a network connection."""
import builtins
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from unittest.mock import patch
import pytest
import requests
import httpx
from fastapi.testclient import TestClient
from backend import app as api
from backend.config import cors_origins
from backend.data_loader import alert_key, default_key, load_dataset


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original=socket.socket.connect
    def deny(*args,**kwargs): raise AssertionError('API must make no network requests')
    def connect(self,address):
        caller=sys._getframe(1)
        # Windows asyncio's local wakeup socketpair is IPC, not an HTTP request.
        if caller.f_code.co_name=='_fallback_socketpair' and caller.f_code.co_filename==socket.__file__ and address[0] in {'127.0.0.1','::1'}:
            return original(self,address)
        return deny()
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(socket,'create_connection',deny)
    monkeypatch.setattr(requests.sessions.Session,'request',deny)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',deny)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',deny)


@pytest.fixture
def client():
    with TestClient(api.create_app()) as c:
        yield c


def test_health_meta_stats_distribution_and_openapi(client):
    h=client.get('/api/v1/health').json()
    assert h['status']=='ok' and h['dataset_loaded'] is True and h['total_hotspots']==674
    m=client.get('/api/v1/meta').json()
    assert m['dataset_mode']=='retrospective_demo' and m['classifier_operational'] is False
    assert m['classification_source']=='rule_based_weak_label_fallback' and m['source_stage']==5
    stats=client.get('/api/v1/stats').json()
    assert stats['class_counts']==dict(industrial=308,wildfire=79,unknown=287)
    assert stats['risk_band_counts']==dict(critical=0,high=10,moderate=149,low=515)
    assert stats['day_night_counts']=={'D':510,'N':164} and stats['confidence_counts']=={'h':3,'l':96,'n':575}
    assert stats['risk_score']==dict(minimum=5,median=13.34,mean=21.85,maximum=60.21)
    dist=client.get('/api/v1/risk-distribution').json()
    assert len(dist['items'])==20 and dist['items'][-1]['hotspot_count']==674
    assert sum(r['hotspot_count'] for r in dist['items'] if r['predicted_class']!='overall' and r['risk_band']!='all')==674
    paths=client.get('/openapi.json').json()['paths']
    assert set(paths)=={'/api/v1/'+p for p in ['health','meta','stats','hotspots','hotspots/{hotspot_id}','hotspots.geojson','alerts','alert-groups','risk-distribution']}
    assert all(paths[p]['get']['summary'] and paths[p]['get']['description'] for p in paths)
    assert client.get('/docs').status_code==200


def test_default_order_pagination_detail_and_nulls(client):
    first=client.get('/api/v1/hotspots').json()
    assert first['total']==674 and first['returned']==first['limit']==100 and first['offset']==0
    expected=sorted(client.app.state.dataset.hotspots,key=default_key)
    assert [h['hotspot_id'] for h in first['items']]==[h.hotspot_id for h in expected[:100]]
    page=client.get('/api/v1/hotspots',params={'offset':100,'limit':3}).json()
    assert [h['hotspot_id'] for h in page['items']]==[h.hotspot_id for h in expected[100:103]]
    assert client.get('/api/v1/hotspots?offset=999').json()['items']==[]
    for h in first['items']:
        assert h['class_probability'] is None and len(h['acq_time'])==4
        assert h['predicted_class'].islower() and h['risk_band'].islower()
    detail=client.get('/api/v1/hotspots/'+first['items'][0]['hotspot_id'])
    assert detail.status_code==200 and detail.json()==first['items'][0]


@pytest.mark.parametrize('params,attribute,predicate',[
    ({'predicted_class':'wildfire'},'predicted_class',lambda v:v=='wildfire'),
    ({'risk_band':'high'},'risk_band',lambda v:v=='high'),
    ({'date_from':'2026-06-12'},'acq_date',lambda v:v>='2026-06-12'),
    ({'date_to':'2026-06-12'},'acq_date',lambda v:v<='2026-06-12'),
    ({'day_night':'N'},'day_night',lambda v:v=='N'),
    ({'min_frp':10},'frp',lambda v:v>=10),
    ({'max_frp':5},'frp',lambda v:v<=5),
    ({'min_risk_score':35},'risk_score',lambda v:v>=35),
    ({'max_risk_score':12},'risk_score',lambda v:v<=12),
    ({'min_persistence':20},'persistence_count_30d',lambda v:v>=20),
    ({'bbox':'72.6,21.1,72.65,21.15'},'longitude',lambda v:72.6<=v<=72.65),
])
def test_every_filter_and_geojson_parity(client,params,attribute,predicate):
    result=client.get('/api/v1/hotspots',params={**params,'limit':500})
    assert result.status_code==200
    page=result.json(); assert page['items'] and all(predicate(h[attribute]) for h in page['items'])
    geo=client.get('/api/v1/hotspots.geojson',params=params).json()
    assert geo['type']=='FeatureCollection' and len(geo['features'])==page['total']
    assert [f['properties']['hotspot_id'] for f in geo['features'][:500]]==[h['hotspot_id'] for h in page['items']]
    for feature in geo['features']:
        lon,lat=feature['geometry']['coordinates']; assert 72<=lon<75 and 21<=lat<24
        assert feature['geometry']['type']=='Point'


def test_combined_and_valid_empty(client):
    q={'predicted_class':'industrial','risk_band':'high','day_night':'N','date_from':'2026-06-12','date_to':'2026-06-12','min_persistence':30,'bbox':'72.6,21.1,72.65,21.15'}
    assert client.get('/api/v1/hotspots',params=q).json()['total']==2
    response=client.get('/api/v1/hotspots?predicted_class=wildfire&risk_band=high')
    assert response.status_code==200 and response.json()['items']==[]


@pytest.mark.parametrize('params',[
    {'predicted_class':'flare'},{'risk_band':'HIGH'},{'day_night':'night'},
    {'min_frp':-1},{'max_frp':'NaN'},{'min_frp':'Infinity'},
    {'min_frp':20,'max_frp':10},{'min_risk_score':100,'max_risk_score':10},{'max_risk_score':101},
    {'min_persistence':0},{'min_persistence':31},{'min_persistence':'1.5'},
    {'date_from':'2026-06-31'},{'date_from':'20260601'},{'date_from':'2026-06-12','date_to':'2026-06-11'},
    {'bbox':'1,2,3'},{'bbox':'73,22,72,21'},{'bbox':'NaN,21,73,22'},{'bbox':'72,21,72,22'},{'bbox':'-181,21,73,22'},
    {'sort_by':'latitude'},{'sort_order':'random'},{'limit':0},{'limit':501},{'offset':-1},{'unexpected':'value'},
])
def test_invalid_filters_consistent_422_no_trace(client,params):
    result=client.get('/api/v1/hotspots',params=params)
    assert result.status_code==422
    assert result.json()['error']['code']=='validation_error'
    assert 'Traceback' not in result.text and 'File "' not in result.text


@pytest.mark.parametrize('field',['acq_date','acq_time','frp','persistence_count_30d','risk_score','predicted_class','risk_band','hotspot_id'])
@pytest.mark.parametrize('direction',['asc','desc'])
def test_sorting_allowlist_deterministic(client,field,direction):
    params={'sort_by':field,'sort_order':direction,'limit':500}
    a=client.get('/api/v1/hotspots',params=params);b=client.get('/api/v1/hotspots',params=params)
    assert a.status_code==200 and a.content==b.content
    items=a.json()['items']; severity={'low':0,'moderate':1,'high':2,'critical':3}
    values=[severity[h[field]] if field=='risk_band' else h[field] for h in items]
    assert values==sorted(values,reverse=direction=='desc')


@pytest.mark.parametrize('identifier',['missing','..','%2e%2e%2fREADME.md','C:%5CWindows%5Cwin.ini'])
def test_path_like_ids_are_only_lookups(client,identifier):
    response=client.get('/api/v1/hotspots/'+identifier)
    assert response.status_code==404 and response.json()['error']['code']=='not_found'


def test_alerts_groups_filtering_order_and_paging(client):
    result=client.get('/api/v1/alerts').json()
    assert result['total']==10 and all(h['risk_band']=='high' for h in result['items'])
    ordered=sorted([h for h in client.app.state.dataset.hotspots if h.risk_band=='high'],key=alert_key)
    assert [h['hotspot_id'] for h in result['items']]==[h.hotspot_id for h in ordered]
    assert client.get('/api/v1/alerts?offset=2&limit=2').json()['items']==result['items'][2:4]
    assert client.get('/api/v1/alerts?predicted_class=unknown').json()['total']==0
    assert client.get('/api/v1/alerts?date_from=2026-06-12&date_to=2026-06-12').json()['total']==2
    groups=client.get('/api/v1/alert-groups').json()
    assert groups['total']==6 and sum(g['hotspot_count'] for g in groups['items'])==10
    assert client.get('/api/v1/alert-groups?date_from=2026-06-12&date_to=2026-06-12').json()['total']==1
    for endpoint in ['alerts','alert-groups']:
        assert client.get('/api/v1/'+endpoint+'?date_from=2026-06-20&date_to=2026-06-01').status_code==422


def test_cors_and_read_only_methods(client,monkeypatch):
    headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'}
    response=client.options('/api/v1/hotspots',headers=headers)
    assert response.status_code==200 and response.headers['access-control-allow-origin']==headers['Origin']
    assert 'access-control-allow-credentials' not in response.headers
    headers['Origin']='https://unapproved.example'
    response=client.options('/api/v1/hotspots',headers=headers)
    assert response.status_code==400 and 'access-control-allow-origin' not in response.headers
    assert client.post('/api/v1/hotspots').status_code==405
    monkeypatch.setenv('FIRE_MONITOR_CORS_ORIGINS','*')
    with pytest.raises(ValueError): cors_origins()
    monkeypatch.setenv('FIRE_MONITOR_CORS_ORIGINS','https://review.example')
    assert 'https://review.example' in cors_origins()


def test_one_startup_load_no_request_disk_io_or_model_usage(monkeypatch):
    count=[];real=api.load_dataset
    def counted(): count.append(1);return real()
    monkeypatch.setattr(api,'load_dataset',counted)
    with TestClient(api.create_app()) as client:
        original=client.app.state.dataset.hotspots[0].model_dump()
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No request disk reads')):
            for _ in range(2):
                for path in ['health','meta','stats','hotspots','hotspots.geojson','alerts','alert-groups','risk-distribution']:
                    assert client.get('/api/v1/'+path).status_code==200
        response=client.get('/api/v1/hotspots').json();response['items'][0]['risk_score']=999
        assert client.app.state.dataset.hotspots[0].model_dump()==original
    assert len(count)==1


def test_isolated_backend_only_startup(tmp_path):
    source=Path(api.__file__).parent; target=tmp_path/'backend'
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__'))
    code="""
import socket,sys
from unittest.mock import patch
from pathlib import Path
from backend.app import create_app
from fastapi.testclient import TestClient
original=socket.socket.connect
def deny(*a,**k): raise AssertionError('No external network')
def connect(self,address):
 frame=sys._getframe(1)
 if frame.f_code.co_name=='_fallback_socketpair' and frame.f_code.co_filename==socket.__file__ and address[0] in {'127.0.0.1','::1'}: return original(self,address)
 return deny()
with patch.object(socket.socket,'connect',connect),patch.object(socket,'create_connection',deny):
 with TestClient(create_app()) as client:
  assert client.get('/api/v1/health').json()['total_hotspots']==674
  assert client.get('/api/v1/alerts').json()['total']==10
  assert client.get('/api/v1/risk-distribution').json()['total_hotspots']==674
assert not any(n=='joblib' or n.startswith('sklearn') or n.startswith('src.') for n in sys.modules)
assert not Path('data').exists() and not Path('outputs').exists() and not Path('models').exists()
print('ISOLATED_BACKEND_ONLY_PASS')
"""
    result=subprocess.run([sys.executable,'-B','-c',code],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'ISOLATED_BACKEND_ONLY_PASS' in result.stdout
