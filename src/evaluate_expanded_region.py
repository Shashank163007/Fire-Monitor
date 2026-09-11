"""Stage 3.6: buffered OSM context and final two-class data-readiness attempt."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
import rasterio
import requests
from shapely.errors import GEOSException

if __package__:
    from . import build_landcover_features as lc
    from .build_features import INDUSTRIAL, MINING, ENDPOINT, convert, matches, nearest_asset, densify
else:
    import build_landcover_features as lc
    from build_features import INDUSTRIAL, MINING, ENDPOINT, convert, matches, nearest_asset, densify

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/osm/expanded_region"
REGION = SimpleNamespace(region_id="expanded_21_24_72_75", min_lat=21, max_lat=24, min_lon=72, max_lon=75)
CELLS = {f"cell_{lat}_{lon}": [lat, lon, lat+1, lon+1] for lat in range(21,24) for lon in range(72,75)}
NATIVE = "hotspot_id latitude longitude acq_date acq_time satellite instrument frp brightness bright_t31 confidence day_night scan track".split()
SORT = "acq_date acq_time latitude longitude satellite hotspot_id".split()
LABELS = ["unknown_context_unavailable", "conflict_excluded", "industrial_candidate", "wildfire_candidate", "cropland_hotspot_candidate", "unknown"]
CLASSES = ["industrial_candidate", "wildfire_candidate"]
LOG = logging.getLogger("expanded")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def inside_study(lat, lon):
    return bool(21 <= lat < 24 and 72 <= lon < 75)


def core_cell(lat, lon):
    return f"cell_{int(np.floor(lat))}_{int(np.floor(lon))}" if inside_study(lat, lon) else None


def buffered(bounds):
    s,w,n,e = bounds
    return [round(s-.02,2), round(w-.02,2), round(n+.02,2), round(e+.02,2)]


def covers(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def selectors():
    return [(k,v) for rules in [INDUSTRIAL,MINING] for k,values in rules.items() for v in (sorted(values) if values else [None])]


def query_for(bounds):
    bbox = "("+",".join(f"{x:.2f}" for x in bounds)+")"
    lines = [f'  nwr["{k}"'+(f'="{v}"' if v is not None else "")+"]"+bbox+";" for k,v in selectors()]
    return "[out:json][timeout:60];\n(\n"+"\n".join(lines)+"\n);\nout body geom;\n"


def compatible_query(query, bounds):
    if "out body geom" not in query:
        return False
    found = re.findall(r'nwr\["([^"]+)"(?:="([^"]+)")?\]\(([^)]+)\);', query)
    compatible = set()
    for key,value,area in found:
        try:
            numbers = [float(x) for x in area.split(",")]
            if len(numbers) == 4 and covers(numbers,bounds): compatible.add((key,value or None))
        except ValueError:
            continue
    return set(selectors()).issubset(compatible)


def compatible_cache(record, bounds, directory=RAW):
    try:
        query = record["query"]
        if record["query_status"] != "success" or record["endpoint"] != ENDPOINT:
            return False
        if record["query_hash"] != hashlib.sha256((ENDPOINT+query).encode()).hexdigest():
            return False
        if not covers(record["buffered_query_bounds"],bounds) or not compatible_query(query,bounds):
            return False
        raw = (Path(directory)/record["response_file"]).read_bytes()
        if len(raw) != record["response_size"] or hashlib.sha256(raw).hexdigest() != record["response_sha256"]:
            return False
        lc.valid_payload(raw)
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def legacy_caches():
    """Expose existing Stage 2.5 caches with their actual unexpanded query areas."""
    report = ROOT/"outputs/demo_region_selection.md"
    if not report.exists(): return []
    candidates = []
    for section in report.read_text(encoding="utf-8").split("### cell_")[1:]:
        try:
            query = section.split("```overpass\n",1)[1].split("```",1)[0]
            detail = json.loads(section.split("```json\n",1)[1].split("```",1)[0])
            bbox = [float(x) for x in re.search(r'\]\(([^)]+)\)',query).group(1).split(",")]
            for request in detail["requests"]:
                if request.get("http_status") == 200 or request.get("status") == "cached":
                    path = ROOT/"data/raw/osm/region_scan"/request["file"]
                    if path.exists():
                        candidates.append(({"query_status":"success", "query":query, "endpoint":detail["endpoint"], "query_hash":hashlib.sha256((detail["endpoint"]+query).encode()).hexdigest(), "buffered_query_bounds":bbox, "response_file":path.name, "response_size":path.stat().st_size, "response_sha256":request["sha256"]},path.parent))
        except (IndexError,KeyError,ValueError,AttributeError):
            continue
    return candidates


def geometry_pools(payload):
    state = {}
    split = {name:{"elements":[e for e in payload["elements"] if matches(e.get("tags",{}),rules)]} for name,rules in [("industrial",INDUSTRIAL),("mining",MINING)]}
    industrial,mining = convert(split,state)
    valid = True
    if state["rejected_geometries"]:
        if split["industrial"]["elements"] and industrial.empty: valid = False
        if split["mining"]["elements"] and mining.empty: valid = False
    state["context_reconstruction_valid"] = valid
    return industrial,mining,state


def add_counts(record, payload):
    try:
        industrial,mining,state = geometry_pools(payload)
        record["feature_counts"] = {"returned_objects":len(payload["elements"]), "industrial":len(industrial), "mining":len(mining)}
        record["geometry_context_valid"] = state["context_reconstruction_valid"]
        record["geometry_audit"] = state
    except (ValueError,KeyError,TypeError,GEOSException) as exc:
        record.update(feature_counts={"returned_objects":len(payload["elements"]),"industrial":None,"mining":None},geometry_context_valid=False,geometry_error=str(exc))
    return record


def fetch_cell(cell_id, directory=RAW, offline=False, session=None, sleep=time.sleep, older=()):
    directory = Path(directory)
    bounds = buffered(CELLS[cell_id])
    path = directory/(cell_id+"_manifest.json")
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if compatible_cache(record,bounds,directory):
            LOG.info("%s: validated cached buffered response",cell_id)
            return lc.valid_payload((directory/record["response_file"]).read_bytes()),record,"cached"
        if offline:
            if record.get("query_status") == "failed": return None,record,"cached_failure"
            raise ValueError(f"Invalid expanded OSM cache for {cell_id}; offline run cannot replace it")
    query = query_for(bounds)
    record = {"core_cell_id":cell_id,"core_bounds":CELLS[cell_id],"buffered_query_bounds":bounds,"endpoint":ENDPOINT,"query":query,"query_hash":hashlib.sha256((ENDPOINT+query).encode()).hexdigest(),"query_status":"failed","response_file":None,"response_sha256":None,"response_size":0,"geometry_context_valid":False,"feature_counts":{"industrial":None,"mining":None},"requests":[]}
    if offline:
        raise RuntimeError(f"Missing expanded OSM manifest for {cell_id}; run acquisition first")
    directory.mkdir(parents=True,exist_ok=True)
    for prior,source in older:
        if compatible_cache(prior,bounds,source):
            raw=(source/prior["response_file"] ).read_bytes()
            name=cell_id+"_reused_"+prior["response_sha256"][:16]+".json"
            (directory/name).write_bytes(raw)
            record.update({k:prior[k] for k in ["query","query_hash","buffered_query_bounds","response_sha256","response_size"]})
            record.update(response_file=name,query_status="success",acquisition="reused_earlier_compatible_cache")
            payload=lc.valid_payload(raw)
            add_counts(record,payload)
            path.write_bytes(json_bytes(record))
            return payload,record,"reused"
    session=session or requests.Session()
    for attempt in range(1,4):
        request={"attempt":attempt}
        try:
            LOG.info("%s: buffered Overpass attempt %d/3",cell_id,attempt)
            response=session.post(ENDPOINT,data={"data":query},headers={"Accept-Encoding":"identity","User-Agent":"SIH26162-expanded-region/3.6"},timeout=(15,90))
            raw=response.content
            sha=hashlib.sha256(raw).hexdigest()
            filename=f"{cell_id}_{record['query_hash'][:12]}_attempt{attempt}_http{response.status_code}_{sha[:12]}.json"
            raw_path=directory/filename
            if not raw_path.exists(): raw_path.write_bytes(raw)
            request.update(http_status=response.status_code,response_file=filename,response_sha256=sha,response_size=len(raw))
            response.raise_for_status()
            payload=lc.valid_payload(raw)
            request["status"]="success"
            record["requests"].append(request)
            record.update(query_status="success",response_file=filename,response_sha256=sha,response_size=len(raw),acquisition="downloaded_stage3_6")
            add_counts(record,payload)
            path.write_bytes(json_bytes(record))
            return payload,record,"downloaded"
        except (requests.RequestException,ValueError,TypeError,AttributeError) as exc:
            request.update(status="failed",error=str(exc))
            record["requests"].append(request)
            LOG.warning("%s request failed: %s",cell_id,exc)
            if attempt<3: sleep(2**attempt)
    record["acquisition"]="failed_stage3_6"
    path.write_bytes(json_bytes(record))
    return None,record,"failed"


def acquire_osm(offline=False):
    payloads,records,runtime={},{},{}
    older=legacy_caches()
    for cell in CELLS:
        payload,record,source=fetch_cell(cell,offline=offline,older=older)
        if payload is not None: payloads[cell]=payload
        records[cell]=record
        runtime[source]=runtime.get(source,0)+1
        if not offline:
            (RAW/"manifest.json").write_bytes(json_bytes({"bounds_order":"south,west,north,east","buffer_degrees":.02,"cells":records}))
    central=json_bytes({"bounds_order":"south,west,north,east","buffer_degrees":.02,"cells":records})
    if offline and (RAW/"manifest.json").read_bytes()!=central:
        raise ValueError("Aggregate OSM manifest differs from per-cell records")
    return payloads,records,runtime


def merge_objects(payloads):
    objects={}
    duplicates=conflicts=0
    for cell,payload in sorted(payloads.items()):
        for item in sorted(payload["elements"],key=lambda e:(e["type"],e["id"])):
            key=(item["type"],item["id"])
            if key in objects:
                duplicates+=1
                conflicts+=int(canonical(objects[key])!=canonical(item))
            else: objects[key]=item
    return {"elements":[objects[k] for k in sorted(objects)]},{"unique_osm_objects":len(objects),"duplicate_occurrences_removed":duplicates,"conflicting_snapshots":conflicts,"conflict_resolution":"first object by alphabetical core-cell ID; preserve distinct OSM type/ID even for overlapping geometry"}


def sorted_rows(frame):
    return frame.sort_values(SORT,kind="stable").reset_index(drop=True)


def select_targets(firms):
    target=lc.select_feature_targets(REGION,firms,"2026-06-01","2026-06-30","2026-05-01",True)
    extra=[c for c in NATIVE if c not in target]
    target=target.merge(firms[["hotspot_id"]+extra],on="hotspot_id",how="left",validate="one_to_one")
    target["core_osm_cell_id"]=[core_cell(a,b) for a,b in zip(target.latitude,target.longitude)]
    return sorted_rows(target[NATIVE+["grid_cell_id","core_osm_cell_id","persistence_count_30d","persistence_history_complete"]])


def sample_cover(src,lon,lat):
    if not inside_study(lat,lon): raise ValueError("Coordinate outside half-open study bounds")
    # Rasterio's north-up bottom edge is exclusive. The study includes 21 N;
    # sample its immediately adjacent interior pixel (shift <0.00001 m).
    adjusted=lat+src.res[1]*1e-6 if lat==src.bounds.bottom else lat
    return lc.sample_landcover(src,lon,adjusted)


def land_valid(row):
    code=row["land_cover_code"]
    return bool(pd.notna(code) and code in lc.CLASSES and row["land_cover_class"]==lc.CLASSES[code] and row["land_cover_sample_status"]=="valid")


def distance_valid(row,category):
    field="distance_to_industrial_km" if category=="industrial" else "nearest_mine_or_quarry_distance_km"
    d=row[field]
    count=row[f"mapped_{category}_object_count"]
    return bool(row[f"{category}_query_success"] and ((pd.isna(d) and pd.notna(count) and count==0) or (pd.notna(d) and np.isfinite(d) and d>=0)))


def label_row(row):
    def result(label,reason,conflict=False):
        return {"weak_label":label,"weak_label_reason":reason,"weak_label_source":"OSM buffered merged geometry + ESA WorldCover 2021 v200 centre pixel","weak_label_conflict":conflict}
    if not row["context_available"] or not land_valid(row) or not all(distance_valid(row,c) for c in ["industrial","mining"]):
        return result("unknown_context_unavailable","Required OSM or WorldCover context unavailable/invalid")
    i,m=row["distance_to_industrial_km"],row["nearest_mine_or_quarry_distance_km"]
    near_i,near_m=pd.notna(i) and i<=1,pd.notna(m) and m<=1
    if near_i and near_m: return result("conflict_excluded","Industrial and mining geometry both within 1 km",True)
    if near_i and not near_m and row["land_cover_class"]!="Permanent water bodies":
        return result("industrial_candidate","Industrial within 1 km; no mapped mining within 1 km; valid non-water centre")
    if not near_i and not near_m:
        if row["land_cover_class"] in {"Tree cover","Shrubland"}:
            return result("wildfire_candidate","Tree/Shrubland centre; successful queries show no mapped industrial/mining object within 1 km")
        if row["land_cover_class"]=="Cropland":
            return result("cropland_hotspot_candidate","Cropland context only; no burning-season evidence; no mapped industrial/mining object within 1 km")
    return result("unknown","No proxy rule satisfied; unknown is not a negative class")


def firms_valid(row):
    positive=["brightness","bright_t31","scan","track"]
    for field in positive+["frp","latitude","longitude"]:
        value=row[field]
        if pd.isna(value) or not np.isfinite(value): return False
        if field in positive and value<=0: return False
    date=str(row["acq_date"])
    time_value=str(row["acq_time"])
    return bool(inside_study(row["latitude"],row["longitude"]) and row["frp"]>=0 and "2026-06-01"<=date<="2026-06-30" and re.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]",time_value) and row["confidence"] in {"l","n","h"} and row["day_night"] in {"D","N"} and all(pd.notna(row[k]) and str(row[k]).strip() for k in ["hotspot_id","satellite","instrument"]))


def training_rows(audit):
    mask=[]
    for row in audit.to_dict("records"):
        mask.append(bool(row["weak_label"] in CLASSES and firms_valid(row) and row["context_available"] and land_valid(row) and all(distance_valid(row,c) for c in ["industrial","mining"]) and row["persistence_history_complete"] and not row["weak_label_conflict"]))
    return sorted_rows(audit.loc[mask].copy())


def readiness(training):
    counts=training.weak_label.value_counts().reindex(CLASSES,fill_value=0)
    i,w=int(counts.iloc[0]),int(counts.iloc[1])
    n=len(training)
    pi,pw=(100*i/n,100*w/n) if n else (None,None)
    history_pct=100*int(training.persistence_history_complete.sum())/n if n else 0.0
    osm_ok=bool(n and all(all(distance_valid(row,c) for c in ["industrial","mining"]) and row["context_available"] for row in training.to_dict("records")))
    conditions={"1_industrial_at_least_20":i>=20,"2_wildfire_at_least_20":w>=20,"3_total_at_least_50":n>=50,"4_neither_class_above_90_percent":bool(n and max(pi,pw)<=90),"5_every_eligible_row_valid_osm":osm_ok,"6_every_eligible_row_valid_worldcover":bool(n and all(land_valid(r) for r in training.to_dict("records"))),"7_history_complete_at_least_80_percent":bool(n and history_pct>=80),"8_no_conflict_rows":bool(not training.weak_label.eq("conflict_excluded").any() and not training.weak_label_conflict.any()),"9_unique_hotspot_id":bool(training.hotspot_id.notna().all() and training.hotspot_id.is_unique)}
    return {"can_lock_region":bool(i and w and all(conditions.values())),"conditions":conditions,"eligible_industrial":i,"eligible_wildfire":w,"total_eligible":n,"industrial_percentage":pi,"wildfire_percentage":pw,"class_balance_ratio":max(i,w)/min(i,w) if i and w else None,"eligible_history_complete_percentage":history_pct}


def coverage_table(records,targets):
    rows=[]
    for cell,r in sorted(records.items()):
        s,w,n,e=r["core_bounds"]
        bs,bw,bn,be=r["buffered_query_bounds"]
        rows.append({"core_osm_cell_id":cell,"min_lat":s,"min_lon":w,"max_lat":n,"max_lon":e,"query_min_lat":bs,"query_min_lon":bw,"query_max_lat":bn,"query_max_lon":be,"june_hotspots":int(targets.core_osm_cell_id.eq(cell).sum()),"query_status":r["query_status"],"geometry_context_valid":r["geometry_context_valid"],"industrial_object_count":r["feature_counts"]["industrial"],"mining_object_count":r["feature_counts"]["mining"],"acquisition":r["acquisition"],"endpoint":r["endpoint"],"query_hash":r["query_hash"],"response_sha256":r["response_sha256"],"response_size":r["response_size"],"response_file":r["response_file"]})
    return pd.DataFrame(rows)


def report(audit,training,coverage,result,merge_state,geometry_state,tile,source_hash):
    lines=["# Stage 3.6 expanded-region readiness", "", "Study: 21 <= latitude < 24, 72 <= longitude < 75. Target: June 1-30, 2026. This is the final region-readiness attempt; all earlier files and outputs remain preserved.","", "**PASS: the expanded region can be locked for the industrial/wildfire two-class June demo scope.**" if result["can_lock_region"] else "**FAIL: the expanded region cannot be locked for classifier training. Recommend the pre-agreed transparent rule-based fallback. Do not initiate another region search.**", "", "No classifier, frontend, final predictions, classified_hotspots.csv or feature_importances.json was created. Training candidates are proxy-labelled observations, not ground truth; no balancing or synthesis was performed.","",f"Total June hotspots: **{len(audit)}**; eligible rows: **{len(training)}**. Complete calendar persistence history: **{int(audit.persistence_history_complete.sum())}/{len(audit)}**.","","| Weak label | Count |","| --- | ---: |"]
    for label in LABELS: lines.append(f"| {label} | {int(audit.weak_label.eq(label).sum())} |")
    lines += ["","## Nine readiness conditions","","| Condition | Result |","| --- | --- |"]
    lines.extend(f"| {k} | {'PASS' if v else 'FAIL'} |" for k,v in result["conditions"].items())
    lines += ["","```json",json.dumps(result,sort_keys=True,indent=2),"```","","## Buffered OSM coverage","","| Core cell | June hotspots | Status | Industrial objects | Mining objects | Initial acquisition |","| --- | ---: | --- | ---: | ---: | --- |"]
    for r in coverage.to_dict("records"):
        lines.append(f"| {r['core_osm_cell_id']} | {r['june_hotspots']} | {r['query_status']} | {r['industrial_object_count']} | {r['mining_object_count']} | {r['acquisition']} |")
    lines += ["","Earlier unbuffered one-degree caches cannot cover the required 1.04-degree query boxes and are rejected for this use. Each core has a 0.02-degree buffer, including outside the study edge. Hotspots remain in their half-open cores. Each raw response and per-query manifest is retained unchanged after acquisition; reruns validate hashes and query compatibility. Initial acquisition is stable provenance, not the current run's cache-hit status. Offline runs preserve failures without retrying.","","Mapped object counts in each audit row refer to usable geometry in its core's buffered response. Distances use the complete deduplicated merged industrial/mining collections from all successful queries. A failed core query makes its rows context-unavailable even if adjacent queries retrieved nearby objects. When the merged pool is empty, distance is missing and successful query/count-zero fields distinguish absence of mapped objects from failure. A core count can be zero while its globally nearest distance is finite to an object outside its query.","","## Method, exclusions and limitations","","Persistence uses actual May 1-June 30 normalized observations and distinct dates per globally anchored 0.01-degree cell in [d-29,d], inclusive. June 1 starts May 3. Complete calendar history is not evidence of daily satellite observation coverage. Grid recurrence is retrospective and includes all detections on the target date. Required native measurements must be valid and nonmissing in training candidates; exclusions remain in the audit.","","Centre-pixel WorldCover remains the label source. Unknown/nodata immediately yields unknown_context_unavailable. Both exact upper study edges (24 N, 75 E) are excluded. At exactly the included south edge (21 N), the new sampling wrapper selects the immediately adjacent interior raster pixel using an inward adjustment below 0.00001 m; older raster functions and outputs are unchanged. Nominal 390 m footprints crossing tile edges are flagged and use valid pixels only.","",f"Clipped footprints: {int(audit.footprint_clipped_at_raster_edge.sum())}. Invalid FIRMS rows excluded from training: {int((~audit.firms_fields_valid).sum())}. Persistence min/median/mean/max: {audit.persistence_count_30d.min()}/{audit.persistence_count_30d.median()}/{audit.persistence_count_30d.mean():.6f}/{audit.persistence_count_30d.max()}.","","Distance reuses the documented WGS84 ellipsoid / hotspot-centred AEQD method with densified polygon edges and geodesic distance to the nearest geometry, not its centroid. The buffer exceeds the 1 km label threshold but cannot guarantee retrieval of huge enclosing OSM polygons without vertices inside the query. Distances beyond the retrieved area may overestimate the true nearest mapped object. OSM tags/geometry, mining-overlap exclusions and 2026 mapping completeness remain limitations. Different OSM IDs are retained despite geometric overlap. Snapshot disagreements for the same ID are recorded and resolved deterministically.","","The 2021 WorldCover map may differ from 2026 land cover. FIRMS detections are not fire boundaries. Cropland context is never agricultural-burning evidence without a defensible burning-season rule; no agburn or flare labels are assigned. VNF remains a blocked optional future source requiring a separate licence/application. OSM proximity and forest/shrubland context are proxy rules, not verified fire causes.","","Direct proxy-label source features reproduce weak-label rules when used as inputs. Report weak-label agreement, not accuracy. A later ablation using only the eight independent FIRMS-derived features in docs/classifier_feature_policy.md is required. Neither result establishes real-world fire-cause accuracy. Neither model was trained.","","Readiness here uses the nine requirements explicitly specified for Stage 3.6. The Stage 3.5 multi-month concentration criterion is not applicable to this June-only request. Training candidates already require complete history; the 80% training-pool test therefore reports 100% when nonempty. Whole-audit history completeness is also reported above.","","## Immutable input provenance and geometry audit","","```json",json.dumps({"normalized_sha256":source_hash,"worldcover_tile":tile,"merged_objects":merge_state,"merged_geometry":geometry_state},sort_keys=True,indent=2,ensure_ascii=False),"```","","Exact queries, response sizes/hashes and all request outcomes: data/raw/osm/expanded_region/manifest.json and the nine per-cell manifests. Deterministic outputs contain no generation timestamp and use sorted JSON keys. Runtime cache-hit counts are logged separately. Calculate full output hashes externally, avoiding a self-referential report checksum."]
    return "\n".join(lines)+"\n"


def artifacts(offline=False):
    tile=lc.cached_worldcover_tile(lc.REGIONS[1])
    if not covers([tile["raster_bounds"][1],tile["raster_bounds"][0],tile["raster_bounds"][3],tile["raster_bounds"][2]],[21,72,24,75]):
        raise ValueError("Cached WorldCover tile does not cover the expanded region")
    source=ROOT/"data/processed/firms_normalized.csv"
    firms=pd.read_csv(source,dtype={"hotspot_id":"string","acq_date":"string","acq_time":"string","version":"string","satellite":"string","instrument":"string"})
    if not firms.hotspot_id.is_unique or firms.hotspot_id.isna().any(): raise ValueError("Invalid source IDs")
    target=select_targets(firms)
    if target.empty: raise ValueError("No June target hotspots")
    payloads,records,runtime=acquire_osm(offline)
    merged,merge_state=merge_objects(payloads)
    industrial,mining,geometry_state=geometry_pools(merged)
    dense_i=np.array([densify(g) for g in industrial.geometry],dtype=object)
    dense_m=np.array([densify(g) for g in mining.geometry],dtype=object)
    additions=[]
    with rasterio.open(lc.RAW/tile["local_filename"]) as src:
        for n,row in enumerate(target.to_dict("records"),1):
            record=records[row["core_osm_cell_id"]]
            success=record["query_status"]=="success"
            di=dm=np.nan
            if success and record["geometry_context_valid"]:
                di=nearest_asset(row["longitude"],row["latitude"],industrial,dense_i)[1]
                dm=nearest_asset(row["longitude"],row["latitude"],mining,dense_m)[1]
            data={"industrial_query_success":success,"mining_query_success":success,"mapped_industrial_object_count":record["feature_counts"]["industrial"],"mapped_mining_object_count":record["feature_counts"]["mining"],"distance_to_industrial_km":di,"nearest_mine_or_quarry_distance_km":dm,**sample_cover(src,row["longitude"],row["latitude"])}
            data["context_available"]=bool(success and record["geometry_context_valid"] and geometry_state["context_reconstruction_valid"] and land_valid(data) and all(distance_valid(data,c) for c in ["industrial","mining"]))
            data.update(label_row(data))
            data["firms_fields_valid"]=firms_valid(row)
            additions.append(data)
            if n%100==0: LOG.info("Merged-geometry feature progress: %d/%d",n,len(target))
    audit=sorted_rows(pd.concat([target,pd.DataFrame(additions)],axis=1))
    for c in ["land_cover_code","mapped_industrial_object_count","mapped_mining_object_count"]: audit[c]=audit[c].astype("Int64")
    training=training_rows(audit)
    coverage=coverage_table(records,target)
    result=readiness(training)
    contents={"data/processed/expanded_region_june_audit.csv":lc.csv_text(audit).encode(),"data/processed/expanded_region_training_candidates.csv":lc.csv_text(training).encode(),"outputs/expanded_region_osm_coverage.csv":lc.csv_text(coverage).encode(),"outputs/expanded_region_readiness.md":report(audit,training,coverage,result,merge_state,geometry_state,tile,lc.checksum(source)).encode("utf-8")}
    return contents,result,runtime


def main(offline=False):
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    try:
        contents,result,runtime=artifacts(offline)
        for relative,content in contents.items(): (ROOT/relative).write_bytes(content)
        print(json.dumps({"readiness":result,"runtime_response_sources":runtime,"output_hashes":{p:hashlib.sha256(b).hexdigest() for p,b in contents.items()}},indent=2))
    except Exception as exc:
        (ROOT/"outputs/expanded_region_readiness.md").write_text(f"# Stage 3.6 blocked\n\n{exc}\n\nDo not use earlier generated outputs as results of this failed run. No classifier or predictions created; no further region search initiated.\n",encoding="utf-8")
        LOG.exception("Expanded-region evaluation failed")
        raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline",action="store_true",help="Require all per-cell manifests; reuse failures and make zero requests")
    args=parser.parse_args()
    main(args.offline)
