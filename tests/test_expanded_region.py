"""Stage 3.6 boundary, cache, label and readiness tests; no live test requests."""
import hashlib
import io
import json
import socket

import numpy as np
import pandas as pd
import pytest
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from src import evaluate_expanded_region as er


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError("Tests may not access the network")
    monkeypatch.setattr(requests.sessions.Session,"request",forbidden)
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr(socket,"create_connection",forbidden)


def sample(i=2,m=2,land=10):
    return {"hotspot_id":"id0","latitude":21.5,"longitude":72.5,"acq_date":"2026-06-01","acq_time":"0630","satellite":"N20","instrument":"VIIRS","frp":10.,"brightness":310.,"bright_t31":290.,"confidence":"n","day_night":"D","scan":.4,"track":.4,"industrial_query_success":True,"mining_query_success":True,"mapped_industrial_object_count":1,"mapped_mining_object_count":1,"distance_to_industrial_km":i,"nearest_mine_or_quarry_distance_km":m,"land_cover_code":land,"land_cover_class":er.lc.class_name(land),"land_cover_sample_status":"valid" if land in er.lc.CLASSES else "nodata_or_unknown","context_available":True,"persistence_count_30d":1,"persistence_history_complete":True,"weak_label_conflict":False,"weak_label":"wildfire_candidate"}


def candidates(i,w):
    rows=[]
    for label,count in [("industrial_candidate",i),("wildfire_candidate",w)]:
        for n in range(count): rows.append({**sample(i=.5 if label=="industrial_candidate" else 2),"hotspot_id":f"{label}{n}","weak_label":label})
    return pd.DataFrame(rows,columns=list(sample()))


def test_nine_half_open_cells_exact_assignment_and_outer_exclusions():
    assert len(er.CELLS)==9
    for cell,(s,w,n,e) in er.CELLS.items():
        assert er.core_cell(s,w)==cell
        assert er.core_cell((s+n)/2,(w+e)/2)==cell
    assert er.core_cell(22,73)=="cell_22_73"
    for lat,lon in [(24,72),(21,75),(24,75),(20.99,72),(21,71.99),(float('nan'),73)]:
        assert er.core_cell(lat,lon) is None
    for lat in [21,21.999,22,22.999,23,23.999]:
        for lon in [72,72.999,73,73.999,74,74.999]:
            assert sum(s<=lat<n and w<=lon<e for s,w,n,e in er.CELLS.values())==1


def test_buffer_and_outer_query_bounds_do_not_expand_hotspot_selection():
    assert er.buffered(er.CELLS['cell_21_72'])==[20.98,71.98,22.02,73.02]
    assert er.buffered(er.CELLS['cell_23_74'])==[22.98,73.98,24.02,75.02]
    query=er.query_for([20.98,71.98,22.02,73.02])
    assert query.count('(20.98,71.98,22.02,73.02)')==len(er.selectors())
    assert er.core_cell(20.99,72.5) is None


def cache_record(tmp_path,bounds):
    query=er.query_for(bounds)
    raw=b'{"elements": []}'
    (tmp_path/'response.json').write_bytes(raw)
    return {"query_status":"success","endpoint":er.ENDPOINT,"query":query,"query_hash":hashlib.sha256((er.ENDPOINT+query).encode()).hexdigest(),"buffered_query_bounds":bounds,"response_file":"response.json","response_size":len(raw),"response_sha256":hashlib.sha256(raw).hexdigest()}


def test_cache_requires_compatible_tags_buffered_area_hash_and_valid_payload(tmp_path):
    bounds=er.buffered(er.CELLS['cell_21_72'])
    record=cache_record(tmp_path,bounds)
    assert er.compatible_cache(record,bounds,tmp_path)
    assert not er.compatible_cache(cache_record(tmp_path,[21,72,22,73]),bounds,tmp_path)
    record=cache_record(tmp_path,[20,71,23,74])
    assert er.compatible_cache(record,bounds,tmp_path)
    assert not er.compatible_query(record['query'].replace('nwr["landuse"="quarry"]','nwr["landuse"="residential"]'),bounds)
    assert not er.compatible_cache({**record,"response_sha256":"0"*64},bounds,tmp_path)
    assert not er.compatible_cache({**record,"query_status":"failed"},bounds,tmp_path)
    bad=b'{"elements":[],"remark":"runtime error"}'
    (tmp_path/'response.json').write_bytes(bad)
    assert not er.compatible_cache({**record,"response_sha256":hashlib.sha256(bad).hexdigest(),"response_size":len(bad)},bounds,tmp_path)


def test_deduplication_uses_type_and_id_not_geometry_overlap():
    node={"type":"node","id":1,"lat":21.5,"lon":73.001,"tags":{"man_made":"works"}}
    way={"type":"way","id":1,"geometry":[],"tags":{}}
    relation={"type":"relation","id":1,"geometry":[],"tags":{}}
    payloads={"cell_b":{"elements":[node,way,relation]},"cell_a":{"elements":[node]}}
    merged,audit=er.merge_objects(payloads)
    assert len(merged['elements'])==3 and audit['duplicate_occurrences_removed']==1
    assert er.merge_objects(dict(reversed(list(payloads.items()))))==(merged,audit)


def test_cross_cell_nearest_distance_uses_entire_merged_collection():
    payloads={"cell_21_72":{"elements":[{"type":"node","id":1,"lat":21.5,"lon":72.8,"tags":{"man_made":"works"}}]},"cell_21_73":{"elements":[{"type":"node","id":2,"lat":21.5,"lon":73.001,"tags":{"man_made":"works"}}]}}
    merged,_=er.merge_objects(payloads)
    industrial,_,_=er.geometry_pools(merged)
    asset,distance=er.nearest_asset(72.999,21.5,industrial)
    assert er.core_cell(21.5,72.999)=='cell_21_72'
    assert asset.osm_id=='node/2' and 0<distance<.3


def test_empty_success_and_failure_are_distinct_and_retries_bounded(tmp_path):
    class Response:
        status_code=200
        content=b'{"elements":[]}'
        def raise_for_status(self): pass
    class Session:
        def __init__(self,fail=False): self.calls=0; self.fail=fail
        def post(self,*args,**kwargs):
            self.calls+=1
            if self.fail: raise requests.Timeout('isolated fixture timeout')
            return Response()
    success=Session()
    payload,record,source=er.fetch_cell('cell_21_72',tmp_path,session=success)
    assert record['query_status']=='success' and record['feature_counts']['mining']==0
    assert source=='downloaded' and success.calls==1
    _,same,source=er.fetch_cell('cell_21_72',tmp_path,offline=True)
    assert same==record and source=='cached'
    failure=Session(True); delays=[]
    payload,record,source=er.fetch_cell('cell_21_73',tmp_path,session=failure,sleep=delays.append)
    assert payload is None and failure.calls==3 and delays==[2,4]
    assert record['query_status']=='failed'
    _,again,source=er.fetch_cell('cell_21_73',tmp_path,offline=True)
    assert again==record and source=='cached_failure'


def test_exact_calendar_window_distinct_dates_and_native_field_preservation():
    rows=[]
    for n,d in enumerate(['2026-05-01','2026-05-02','2026-05-03','2026-05-03','2026-05-31','2026-06-01','2026-07-01']):
        rows.append({**sample(),"acq_date":d,"hotspot_id":f'id{n}'})
    rows.extend([{**sample(),"latitude":24,"hotspot_id":"north"},{**sample(),"longitude":75,"hotspot_id":"east"}])
    result=er.select_targets(pd.DataFrame(rows))
    assert len(result)==1 and result.persistence_count_30d.tolist()==[3]
    assert result.persistence_history_complete.tolist()==[True]
    assert result.acq_time.tolist()==['0630'] and all(c in result for c in er.NATIVE)
    assert er.lc.persistence_window('2026-06-01')[0]==pd.Timestamp('2026-05-03')


@pytest.mark.parametrize('i,m,land,label',[(.5,.5,40,'conflict_excluded'),(.5,2,40,'industrial_candidate'),(.5,2,10,'industrial_candidate'),(.5,2,80,'unknown'),(2,2,10,'wildfire_candidate'),(2,2,20,'wildfire_candidate'),(2,2,40,'cropland_hotspot_candidate'),(2,.5,10,'unknown'),(2,2,30,'unknown')])
def test_exact_weak_label_priority(i,m,land,label):
    result=er.label_row(sample(i,m,land))
    assert result['weak_label']==label and result['weak_label_conflict']==(label=='conflict_excluded')
    assert result['weak_label'] not in {'agburn','agricultural_burn_candidate','flare'}


def test_unavailable_context_precedes_conflict_and_empty_success_can_be_clear():
    row=sample(.1,.1)
    row['context_available']=False
    assert er.label_row(row)['weak_label']=='unknown_context_unavailable'
    assert er.label_row(sample(.1,.1,0))['weak_label']=='unknown_context_unavailable'
    row=sample(np.nan,np.nan)
    row.update(mapped_industrial_object_count=0,mapped_mining_object_count=0)
    assert er.label_row(row)['weak_label']=='wildfire_candidate'
    row['mining_query_success']=False
    assert er.label_row(row)['weak_label']=='unknown_context_unavailable'
    row=sample(.1,.1); row['industrial_query_success']=False
    assert er.label_row(row)['weak_label']=='unknown_context_unavailable'


def test_training_filter_excludes_bad_measurements_history_context_and_labels():
    rows=[{**sample(),"hotspot_id":"valid"}]
    for n,changes in enumerate([{"weak_label":"cropland_hotspot_candidate"},{"weak_label":"conflict_excluded","weak_label_conflict":True},{"persistence_history_complete":False},{"brightness":np.nan},{"bright_t31":np.nan},{"scan":0},{"industrial_query_success":False},{"land_cover_code":0},{"acq_time":"2460"}]):
        rows.append({**sample(),"hotspot_id":f'bad{n}',**changes})
    result=er.training_rows(pd.DataFrame(rows))
    assert result.hotspot_id.tolist()==['valid']


@pytest.mark.parametrize('i,w,ready',[(30,20,True),(20,30,True),(19,31,False),(31,19,False),(25,24,False),(180,20,True),(181,20,False),(0,50,False),(50,0,False),(0,0,False)])
def test_readiness_thresholds_and_zero_class_balance(i,w,ready):
    result=er.readiness(candidates(i,w))
    assert result['can_lock_region'] is ready
    assert result['class_balance_ratio']==(max(i,w)/min(i,w) if i and w else None)


def test_readiness_context_conflicts_unique_ids_and_history_limits():
    pool=candidates(30,20)
    pool.loc[:9,'persistence_history_complete']=False
    assert er.readiness(pool)['conditions']['7_history_complete_at_least_80_percent']
    pool.loc[10,'persistence_history_complete']=False
    assert not er.readiness(pool)['conditions']['7_history_complete_at_least_80_percent']
    pool.loc[0,'industrial_query_success']=False
    pool.loc[1,'land_cover_sample_status']='nodata_or_unknown'
    pool.loc[2,'weak_label_conflict']=True
    pool.loc[3,'hotspot_id']=pool.hotspot_id.iloc[4]
    conditions=er.readiness(pool)['conditions']
    for key in ['5_every_eligible_row_valid_osm','6_every_eligible_row_valid_worldcover','8_no_conflict_rows','9_unique_hotspot_id']:
        assert not conditions[key]


def test_included_south_edge_and_excluded_upper_edges_sample_correctly():
    with MemoryFile() as mem:
        with mem.open(driver='GTiff',width=12,height=12,count=1,dtype='uint8',crs='EPSG:4326',transform=from_origin(72,24,.25,.25),nodata=0) as dst:
            dst.write(np.full((12,12),10,dtype='uint8'),1)
        with mem.open() as src:
            assert er.sample_cover(src,72,21)['land_cover_code']==10
            for lon,lat in [(72,24),(75,21)]:
                with pytest.raises(ValueError): er.sample_cover(src,lon,lat)


def test_sort_includes_satellite_before_hotspot_and_is_byte_deterministic():
    frame=pd.DataFrame([{**sample(),"satellite":"B","hotspot_id":"a"},{**sample(),"satellite":"A","hotspot_id":"z"}])
    ordered=er.sorted_rows(frame)
    assert ordered.hotspot_id.tolist()==['z','a']
    assert er.lc.csv_text(ordered)==er.lc.csv_text(er.sorted_rows(frame.iloc[::-1]))


def test_real_buffered_cache_execution_is_offline_and_byte_identical():
    contents,result,runtime=er.artifacts(offline=True)
    assert sum(runtime.values())==9 and set(runtime)<={'cached','cached_failure'}
    for path,data in contents.items(): assert data==(er.ROOT/path).read_bytes()
    audit=pd.read_csv(io.BytesIO(contents['data/processed/expanded_region_june_audit.csv']),dtype={'acq_time':'string','satellite':'string'})
    training=pd.read_csv(io.BytesIO(contents['data/processed/expanded_region_training_candidates.csv']),dtype={'acq_time':'string','satellite':'string'})
    assert len(audit)==674 and audit.hotspot_id.is_unique
    assert audit.equals(er.sorted_rows(audit))
    assert set(audit.core_osm_cell_id)==set(er.CELLS)
    assert set(training.weak_label)<=set(er.CLASSES)
    assert training.persistence_history_complete.all() and training.context_available.all()
