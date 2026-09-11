"""Stage 4: spatially grouped Random Forest weak-label agreement, never verified cause."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from pathlib import Path
from decimal import Decimal, ROUND_FLOOR
import sys
import tempfile

sys.dont_write_bytecode = True
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from src import evaluate_expanded_region as er
from src.build_features import GEOD

SEED = 26162
CONFIG = dict(n_estimators=400,class_weight="balanced",random_state=SEED,n_jobs=-1,min_samples_leaf=2,max_features="sqrt")
NATIVE = "frp brightness bright_t31 confidence day_night persistence_count_30d scan track".split()
CONTEXT = ["distance_to_industrial_km","distance_to_mining_km","land_cover_class"]
TARGET_MAP = {"industrial_candidate":"industrial","wildfire_candidate":"wildfire"}
CLASSES = ["industrial","wildfire"]
EXPECTED = {"industrial_candidate":308,"wildfire_candidate":79,"cropland_hotspot_candidate":208,"unknown":79,"conflict_excluded":0,"unknown_context_unavailable":0}
CONTRACT = "hotspot_id latitude longitude acq_date acq_time frp brightness confidence day_night distance_to_industrial_km persistence_count_30d land_cover_class predicted_class class_probability risk_score risk_band".split()
NEAR_METRES = 390.0
MODEL_NAMES = ["contextual","firms_only"]
STAGE4_PATHS = {"src/train_classifier.py","tests/test_classifier.py","docs/model_card.md","docs/stage4_code_review.md","models/contextual_random_forest.joblib","models/firms_only_random_forest.joblib","data/processed/classified_hotspots.csv","outputs/feature_importances.json","outputs/classifier_metrics.json","outputs/classifier_evaluation.md","outputs/confusion_matrix_contextual.csv","outputs/confusion_matrix_firms_only.csv"}
LOG = logging.getLogger("classifier")


def json_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8")


def sha(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()


def protected_hashes():
    files=[p for directory in ["src","tests","docs","outputs","data"] for p in (ROOT/directory).rglob('*') if p.is_file()]
    files += [ROOT/"README.md",ROOT/"requirements.txt"]
    return {str(p.relative_to(ROOT)):sha(p) for p in files if p.relative_to(ROOT).as_posix() not in STAGE4_PATHS}


def atomic_publish(contents, root=ROOT):
    """Compute all artifacts first; replace each final file atomically on its filesystem."""
    for relative,data in contents.items():
        destination=Path(root)/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode="wb",dir=destination.parent,prefix=".stage4-",suffix=".tmp",delete=False) as stream:
                temporary=Path(stream.name)
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,destination)
        finally:
            if temporary is not None and temporary.exists(): temporary.unlink()


def read_inputs():
    dtype={c:"string" for c in ["hotspot_id","acq_date","acq_time","satellite","instrument","confidence"]}
    audit=pd.read_csv(ROOT/"data/processed/expanded_region_june_audit.csv",dtype=dtype)
    training=pd.read_csv(ROOT/"data/processed/expanded_region_training_candidates.csv",dtype=dtype)
    report=(ROOT/"outputs/expanded_region_readiness.md").read_text(encoding="utf-8")
    readiness=json.loads(report.split("```json\n",1)[1].split("```",1)[0])
    validate_inputs(audit,training,readiness)
    return er.sorted_rows(audit),er.sorted_rows(training)


def validate_inputs(audit,training,readiness):
    required=set(er.NATIVE+NATIVE+["distance_to_industrial_km","land_cover_code","land_cover_class","land_cover_sample_status","context_available","industrial_query_success","mining_query_success","mapped_industrial_object_count","mapped_mining_object_count","nearest_mine_or_quarry_distance_km","persistence_history_complete","weak_label","weak_label_conflict","firms_fields_valid"])
    for name,frame in [("audit",audit),("training",training)]:
        missing=required-set(frame)
        if missing: raise ValueError(f"{name}: missing required columns {sorted(missing)}")
        if frame.hotspot_id.isna().any() or not frame.hotspot_id.is_unique: raise ValueError(f"{name}: duplicate/missing hotspot IDs")
        if not (frame.latitude.between(21,24,inclusive="left") & frame.longitude.between(72,75,inclusive="left")).all(): raise ValueError(f"{name}: coordinates outside locked region")
        dates=pd.to_datetime(frame.acq_date,format="%Y-%m-%d",errors="coerce")
        if dates.isna().any() or not dates.between("2026-06-01","2026-06-30").all(): raise ValueError(f"{name}: acquisition dates outside June 2026")
        if not frame.acq_time.str.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]").fillna(False).all(): raise ValueError(f"{name}: invalid HHMM acquisition time")
    if len(audit)!=674 or audit.weak_label.value_counts().to_dict()!={k:v for k,v in EXPECTED.items() if v}: raise ValueError("Stage 3.6 audit counts differ from locked 674-row label distribution")
    if len(training)!=387 or training.weak_label.value_counts().to_dict()!={"industrial_candidate":308,"wildfire_candidate":79}: raise ValueError("Stage 3.6 training counts differ from locked 387 / 308 / 79")
    if training.weak_label_conflict.ne(False).any(): raise ValueError("Conflicts entered training")
    for c in ["context_available","industrial_query_success","mining_query_success","persistence_history_complete","firms_fields_valid"]:
        if training[c].isna().any() or not training[c].eq(True).all(): raise ValueError(f"Training requires valid {c}")
    if not all(er.land_valid(r) and all(er.distance_valid(r,c) for c in ["industrial","mining"]) for r in training.to_dict("records")): raise ValueError("Invalid OSM/WorldCover training context")
    eligible=audit.loc[audit.weak_label.isin(TARGET_MAP)]
    if set(eligible.hotspot_id)!=set(training.hotspot_id): raise ValueError("Training IDs differ from eligible audit subset")
    try:
        pd.testing.assert_frame_equal(eligible.set_index("hotspot_id").sort_index()[training.columns.drop("hotspot_id")],training.set_index("hotspot_id").sort_index(),check_dtype=False)
    except AssertionError as exc: raise ValueError("Training rows differ from their audit observations") from exc
    actual=er.readiness(training)
    if readiness!=actual or not actual["can_lock_region"]: raise ValueError("Stage 3.6 readiness decision differs from accepted PASS; stop")


def normalize_confidence(values):
    """Finite numeric confidence in [0,100] is unchanged; documented ordinal names map 0/1/2."""
    text=values.astype("string").str.strip().str.lower()
    numeric=pd.to_numeric(text,errors="coerce").astype(float)
    numeric=numeric.where(np.isfinite(numeric) & numeric.between(0,100))
    mapping={"l":0.,"low":0.,"n":1.,"nominal":1.,"h":2.,"high":2.}
    categorical=text.map(mapping).astype(float)
    result=numeric.where(numeric.notna(),categorical)
    unexpected=text.notna() & text.ne("") & result.isna()
    return result,int(unexpected.sum())


def feature_names(model, mining=True):
    if model not in MODEL_NAMES: raise ValueError("Unknown model feature set")
    return NATIVE + (["distance_to_industrial_km"]+(["distance_to_mining_km"] if mining else [])+["land_cover_class"] if model=="contextual" else [])


def feature_frame(frame,model,mining=True):
    names=feature_names(model,mining)
    result=frame.copy()
    if "distance_to_mining_km" in names:
        result["distance_to_mining_km"]=result["nearest_mine_or_quarry_distance_km"]
    return result[names].copy()


class FeatureCleaner(TransformerMixin,BaseEstimator):
    """Stateless normalization in the fitted pipeline; learned imputation is downstream."""
    def __init__(self,features): self.features=features
    def fit(self,X,y=None):
        if list(X.columns)!=list(self.features): raise ValueError("Feature matrix violates explicit allowlist")
        self.feature_names_in_=np.asarray(self.features,dtype=object)
        self.n_features_in_=len(self.features)
        return self
    def transform(self,X):
        if list(X.columns)!=list(self.features): raise ValueError("Feature matrix contains missing or forbidden fields")
        out=X.copy()
        for c in self.features:
            if c in {"day_night","land_cover_class"}:
                values=out[c].astype("string").str.strip().str.lower()
                out[c]=values.where(values.ne("")).astype(object).where(values.notna() & values.ne(""),np.nan)
            elif c=="confidence": out[c]=normalize_confidence(out[c])[0]
            else:
                values=pd.to_numeric(out[c],errors="coerce").astype(float)
                valid=np.isfinite(values)
                if c in {"frp","persistence_count_30d","distance_to_industrial_km","distance_to_mining_km"}: valid &= values.ge(0)
                if c in {"brightness","bright_t31","scan","track"}: valid &= values.gt(0)
                out[c]=values.where(valid)
        return out
    def get_feature_names_out(self,input_features=None): return np.asarray(self.features,dtype=object)


def make_pipeline(model,mining=True):
    names=feature_names(model,mining)
    categorical=[c for c in names if c in {"day_night","land_cover_class"}]
    numeric=[c for c in names if c not in categorical]
    preprocessing=ColumnTransformer([("numeric",SimpleImputer(strategy="median",keep_empty_features=True),numeric),("categorical",Pipeline([("imputer",SimpleImputer(strategy="most_frequent",keep_empty_features=True)),("encoder",OneHotEncoder(handle_unknown="ignore",sparse_output=False))]),categorical)],remainder="drop")
    return Pipeline([("clean",FeatureCleaner(names)),("preprocess",preprocessing),("forest",RandomForestClassifier(**CONFIG))])


def deterministic_proba(pipeline,X):
    # Training uses n_jobs=-1 as requested. Serial prediction fixes floating-point
    # accumulation order; values remain sklearn's raw, uncalibrated predict_proba.
    forest=pipeline.named_steps["forest"]
    original=forest.n_jobs
    try:
        forest.n_jobs=1
        probabilities=pipeline.predict_proba(X)
    finally: forest.n_jobs=original
    if not np.isfinite(probabilities).all() or (probabilities<0).any() or (probabilities>1).any(): raise ValueError("Invalid raw model probabilities")
    return probabilities


def near_pairs(frame):
    pairs=[]
    lat,lon=frame.latitude.to_numpy(),frame.longitude.to_numpy()
    for i in range(len(frame)-1):
        distances=GEOD.inv(np.full(len(frame)-i-1,lon[i]),np.full(len(frame)-i-1,lat[i]),lon[i+1:],lat[i+1:])[2]
        pairs.extend((i,int(j)) for j in np.flatnonzero(np.asarray(distances)<=NEAR_METRES)+i+1)
    return pairs


def spatial_groups(frame,size,pairs):
    bins=[(int((Decimal(str(a))/Decimal(str(size))).to_integral_value(rounding=ROUND_FLOOR)),int((Decimal(str(b))/Decimal(str(size))).to_integral_value(rounding=ROUND_FLOOR))) for a,b in zip(frame.latitude,frame.longitude)]
    parent={b:b for b in bins}
    def root(b):
        while parent[b]!=b:
            parent[b]=parent[parent[b]]; b=parent[b]
        return b
    for i,j in pairs:
        a,b=sorted([root(bins[i]),root(bins[j])]); parent[b]=a
    return np.array([f"g{size}_{root(b)[0]}_{root(b)[1]}" for b in bins])


def duplicate_audit(frame,pairs):
    observation=["latitude","longitude","acq_date","acq_time","satellite","instrument"]
    datetimes=pd.to_datetime(frame.acq_date+frame.acq_time,format="%Y-%m-%d%H%M")
    likely=sum(frame.satellite.iloc[i]==frame.satellite.iloc[j] and frame.instrument.iloc[i]==frame.instrument.iloc[j] and abs((datetimes.iloc[i]-datetimes.iloc[j]).total_seconds())<=60 for i,j in pairs)
    return {"duplicate_hotspot_ids":int(frame.hotspot_id.duplicated().sum()),"exact_observation_duplicates_beyond_first":int(frame.duplicated(observation).sum()),"duplicate_coordinate_rows_beyond_first":int(frame.duplicated(["latitude","longitude"]).sum()),"near_coordinate_pairs_within_390m":len(pairs),"likely_same_overpass_pairs_within_390m_and_60s":int(likely),"rows_removed":0,"policy":"Merge initial grid groups for all coordinate pairs within 390 m across all dates; preserve legitimate temporal observations"}


def choose_folds(frame,y,pairs):
    attempts=[]
    for size,k in [(.1,5),(.1,3),(.05,5),(.05,3)]:
        groups=spatial_groups(frame,size,pairs)
        attempt={"grid_degrees":size,"fold_count":k,"spatial_groups":len(set(groups)),"rejection_reasons":[]}
        if len(set(groups))<k: attempt["rejection_reasons"].append(f"Only {len(set(groups))} groups for {k} folds")
        for label in CLASSES:
            n=len(set(groups[np.asarray(y)==label]))
            if n<k: attempt["rejection_reasons"].append(f"{label} occurs in only {n} groups for {k} validation folds")
        folds=[]
        if not attempt["rejection_reasons"]:
            folds=list(StratifiedGroupKFold(n_splits=k,shuffle=True,random_state=SEED).split(frame,y,groups))
            for index,(train,validation) in enumerate(folds,1):
                if set(groups[train]) & set(groups[validation]): attempt["rejection_reasons"].append(f"Fold {index} shares groups")
                for role,indices in [("training",train),("validation",validation)]:
                    counts=pd.Series(np.asarray(y)[indices]).value_counts()
                    if set(counts.index)!=set(CLASSES) or counts.min()<2:
                        attempt["rejection_reasons"].append(f"Fold {index} {role} needs at least two observations per class; counts={counts.to_dict()}")
                validation_set=set(validation)
                if any((i in validation_set)!=(j in validation_set) for i,j in pairs): attempt["rejection_reasons"].append(f"Fold {index} divides near observations")
        attempt["accepted"]=not attempt["rejection_reasons"]
        attempts.append(attempt)
        if attempt["accepted"]: return groups,folds,attempts
    return None,None,attempts


def metrics_for(y,predicted,p_wildfire):
    precision,recall,f1,support=precision_recall_fscore_support(y,predicted,labels=CLASSES,zero_division=0)
    return {"confusion_matrix":confusion_matrix(y,predicted,labels=CLASSES).tolist(),"class_order":CLASSES,"per_class":{c:{"precision":float(precision[i]),"recall":float(recall[i]),"f1":float(f1[i]),"support":int(support[i])} for i,c in enumerate(CLASSES)},"macro_f1":float(f1.mean()),"weighted_f1":float(np.average(f1,weights=support)),"balanced_accuracy":float(balanced_accuracy_score(y,predicted)),"roc_auc":float(roc_auc_score(np.asarray(y)=="wildfire",p_wildfire)) if len(set(y))==2 else None}


def cross_validate(frame,y,groups,folds,model,mining):
    X=feature_frame(frame,model,mining)
    predictions=np.empty(len(frame),dtype=object); probs=np.zeros(len(frame)); assignment=np.zeros(len(frame),dtype=int)
    reports=[]
    for index,(train,validation) in enumerate(folds,1):
        pipeline=make_pipeline(model,mining)
        pipeline.fit(X.iloc[train],y[train])
        probability=deterministic_proba(pipeline,X.iloc[validation])
        classes=pipeline.named_steps["forest"].classes_
        predicted=classes[np.argmax(probability,axis=1)]
        p_wildfire=probability[:,list(classes).index("wildfire")]
        predictions[validation]=predicted; probs[validation]=p_wildfire; assignment[validation]=index
        reports.append({"fold":index,"training_rows":len(train),"validation_rows":len(validation),"training_class_distribution":pd.Series(y[train]).value_counts().to_dict(),"validation_class_distribution":pd.Series(y[validation]).value_counts().to_dict(),"training_spatial_groups":len(set(groups[train])),"validation_spatial_groups":len(set(groups[validation])),"leakage_check":{"no_shared_spatial_groups":not bool(set(groups[train]) & set(groups[validation])),"preprocessing_fit_on_training_fold_only":True,"direct_label_source_features_present":model=="contextual"},**metrics_for(y[validation],predicted,p_wildfire)})
        LOG.info("%s fold %d: weak-label macro F1 %.4f; wildfire recall %.4f",model,index,reports[-1]["macro_f1"],reports[-1]["per_class"]["wildfire"]["recall"])
    if (assignment==0).any(): raise ValueError("Incomplete out-of-fold predictions")
    mean={"macro_f1":float(np.mean([r["macro_f1"] for r in reports])),"wildfire_recall":float(np.mean([r["per_class"]["wildfire"]["recall"] for r in reports])),"balanced_accuracy":float(np.mean([r["balanced_accuracy"] for r in reports])),"roc_auc":float(np.mean([r["roc_auc"] for r in reports]))}
    oof=[{"hotspot_id":frame.hotspot_id.iloc[i],"spatial_group":groups[i],"fold":int(assignment[i]),"reference_candidate_class":y[i],"predicted_candidate_class":predictions[i],"raw_wildfire_probability":float(probs[i])} for i in range(len(frame))]
    return {"feature_list":list(X.columns),"folds":reports,"mean_fold_metrics":mean,"overall_out_of_fold":{**metrics_for(y,predictions,probs),"validation_rows":len(frame),"training_rows_per_fold":[r["training_rows"] for r in reports],"spatial_groups":len(set(groups)),"class_distribution":pd.Series(y).value_counts().to_dict(),"no_shared_spatial_groups":all(r["leakage_check"]["no_shared_spatial_groups"] for r in reports)},"out_of_fold_predictions":oof}


def go_no_go(ablation,failures=False):
    folds=ablation.get("folds",[])
    mean=ablation.get("mean_fold_metrics",{})
    conditions={"at_least_three_valid_spatial_folds":len(folds)>=3,"no_shared_spatial_groups":bool(folds) and all(r["leakage_check"]["no_shared_spatial_groups"] for r in folds),"both_classes_in_every_validation_fold":bool(folds) and all(all(r["validation_class_distribution"].get(c,0)>0 for c in CLASSES) for r in folds),"mean_macro_f1_at_least_0_75":mean.get("macro_f1",-1)>=.75,"mean_wildfire_recall_at_least_0_60":mean.get("wildfire_recall",-1)>=.60,"no_pipeline_metric_or_validation_failures":not failures}
    passed=all(conditions.values())
    return {"classifier_passes":passed,"operational_method":"firms_only_random_forest" if passed else "rule_based_weak_label_fallback","conditions":conditions}


def parent_importances(pipeline):
    preprocessing=pipeline.named_steps["preprocess"]
    numeric=preprocessing.transformers_[0][2]
    cat_names=preprocessing.transformers_[1][2]
    categories=preprocessing.named_transformers_["categorical"].named_steps["encoder"].categories_
    parents=list(numeric)+[name for name,values in zip(cat_names,categories) for _ in values]
    values=pipeline.named_steps["forest"].feature_importances_
    if len(parents)!=len(values): raise ValueError("Feature-importance parent mapping mismatch")
    totals={name:0.0 for name in pipeline.named_steps["clean"].features}
    for name,value in zip(parents,values): totals[name]+=float(value)
    if not np.isclose(sum(totals.values()),1.0,atol=1e-9): raise ValueError("Feature importances do not sum to one")
    return [{"feature":name,"importance":value} for name,value in sorted(totals.items(),key=lambda x:(-x[1],x[0]))]


def inference(audit,training,pipeline,decision):
    output=er.sorted_rows(audit)[CONTRACT[:12]].copy()
    output["predicted_class"]="unknown"; output["class_probability"]=np.nan
    ids=training.hotspot_id.tolist()
    selected=output.hotspot_id.isin(ids)
    if decision["classifier_passes"]:
        if pipeline is None: raise ValueError("Operational pipeline missing")
        rows=training.set_index("hotspot_id").loc[output.loc[selected,"hotspot_id"]].reset_index()
        probability=deterministic_proba(pipeline,feature_frame(rows,"firms_only"))
        classes=pipeline.named_steps["forest"].classes_
        output.loc[selected,"predicted_class"]=classes[np.argmax(probability,axis=1)]
        output.loc[selected,"class_probability"]=probability.max(axis=1)
    else:
        mapping=training.set_index("hotspot_id").weak_label.map(TARGET_MAP)
        output.loc[selected,"predicted_class"]=output.loc[selected,"hotspot_id"].map(mapping)
    output["risk_score"]=np.nan; output["risk_band"]=pd.NA
    validate_output(output,set(ids),decision["classifier_passes"])
    return output


def validate_output(output,eligible_ids,classifier_passes):
    if list(output.columns)!=CONTRACT or len(output)!=674 or output.hotspot_id.isna().any() or not output.hotspot_id.is_unique: raise ValueError("Invalid 674-row classified interface")
    if not set(output.predicted_class)<={"industrial","wildfire","unknown"}: raise ValueError("Unexpected output class")
    noneligible=~output.hotspot_id.isin(eligible_ids)
    if not output.loc[noneligible,"predicted_class"].eq("unknown").all() or output.loc[noneligible,"class_probability"].notna().any(): raise ValueError("Non-eligible rows must remain unknown with null probabilities")
    probabilities=output.class_probability.dropna()
    if not probabilities.between(0,1).all() or not np.isfinite(probabilities).all(): raise ValueError("Probability out of range")
    if classifier_passes and output.loc[~noneligible,"class_probability"].isna().any(): raise ValueError("Eligible classifier probability missing")
    if not classifier_passes and len(probabilities): raise ValueError("Rule fallback may not invent probabilities")
    if output[["risk_score","risk_band"]].notna().any().any(): raise ValueError("Risk fields must remain null")


def evaluation_report(metrics):
    decision=metrics["decision"]
    lines=["# Stage 4 binary proxy-label classification", "", f"Operational method: **{decision['operational_method']}**. This decision uses only FIRMS-only spatial cross-validation and fixed gate thresholds; the contextual model cannot qualify the classifier.","", "Region: 21 <= latitude < 24, 72 <= longitude < 75; June 1-30, 2026. Inputs: 674 audit rows and 387 eligible rows (308 industrial candidates / 79 wildfire candidates). Reference labels are proxies, not verified fire causes.","","## Spatial validation","","```json",json.dumps({"attempts":metrics["spatial_configuration_attempts"],"duplicates":metrics["duplicate_control"]},indent=2,sort_keys=True),"```","","Initial grid groups are conservatively merged when any two coordinates are within 390 m, across all dates, preventing near-repeat observations across grid boundaries from being split. This is a nominal VIIRS-scale proximity criterion, not proof of duplicate identity; no rows are removed. Exact observation keys also include UTC date/time and satellite/instrument. Each accepted training and validation fold must contain at least two rows per class, the predeclared minimum for nondegenerate metrics. Rejected configurations reflect the fixed-seed splitter result; they do not prove no other possible partition exists. No alternative seed or hyperparameter tuning was tried.","","## Weak-label agreement","","The table reports unweighted means across validation folds. Overall pooled out-of-fold metrics, confusion matrices, class precision/recall/F1, class counts, group counts and individual OOF predictions are in classifier_metrics.json.","","| Model | Mean macro F1 | Mean wildfire recall | Mean balanced accuracy against proxies | Mean ROC-AUC |","| --- | ---: | ---: | ---: | ---: |"]
    for name,model in metrics["models"].items():
        m=model["mean_fold_metrics"]
        lines.append(f"| {name} | {m['macro_f1']:.6f} | {m['wildfire_recall']:.6f} | {m['balanced_accuracy']:.6f} | {m['roc_auc']:.6f} |")
    lines += ["",f"Contextual minus FIRMS-only mean macro F1: {metrics.get('contextual_minus_ablation_macro_f1')}. A large contextual advantage may indicate dependence on the same industrial/mining and land-cover evidence used to create labels. The FIRMS-only ablation excludes every direct contextual label-source feature; it still measures agreement with imperfect proxies.","","## Operational gate","","```json",json.dumps(decision,indent=2,sort_keys=True),"```","","## Reproducibility, inference and limits","","Both models use the specified 400-tree balanced Random Forest, seed 26162, min_samples_leaf=2 and max_features=sqrt. Training uses n_jobs=-1. Raw predict_proba is evaluated with serial tree accumulation to stabilize floating-point ordering, then n_jobs=-1 is restored before saving. No imputer or encoder is fitted before fold separation; stateless cleaning is part of each pipeline. No synthetic observations, resampling or validation tuning are used.","","All eligible rows are used for final fits only after both cross-validation evaluations finish. Final-file inference on those same eligible rows is an in-sample batch artifact, not a second evaluation. Non-eligible rows remain unknown. Classifier probabilities, if the FIRMS-only gate passes, are raw uncalibrated model confidence, not verified real-world probabilities. Rule fallback uses eligible candidate classes and null probabilities for every row. Risk score/band remain null.","","The supplied confidence values are l/n/h; they map to explicitly ordered 0/1/2, with low/nominal/high aliases supported. Finite numeric confidence in [0,100] is preserved; unexpected values become missing and are counted. Mixing numeric and ordinal scales warrants separate review in future data; it does not occur in this accepted dataset. Numeric invalid measurements become missing and use fold-trained medians; categorical normalization uses whitespace/case cleanup, fold-trained most-frequent imputation and unknown-safe one-hot encoding.","","Stage 3.6 nearest_mine_or_quarry_distance_km is aliased to distance_to_mining_km only for Model A when all eligible values are finite/nonnegative. IDs, coordinates, cells, dates, target, proxy reasons, output/risk fields and footprint summaries are never classifier inputs. Existing persistence is retrospective through acquisition DATE, not an acquisition-time live feature: no observations after that date enter it, but same-day later detections can. OSM is a later static mapping snapshot, and WorldCover 2021 may not reflect June 2026. These contextual timing limits are another reason Model A is diagnostic only.","","Spatial grouping reduces local repeat leakage but cannot prove independent fire events. The single region/month, small wildfire sample, proxy selection bias and residual longer-range similarity limit generalization. Group-aware folds are not a prospective temporal evaluation. Impurity feature importance describes model splits, not causes; no SHAP values were fabricated.","","Stage 4 explicitly permits unknown in the 16-field classified interface and requests separate contextual/FIRMS-only importance lists with metadata. Those current instructions supersede the older class-enum and single-list importance examples; historical contracts are preserved unchanged. No frontend, alert system, risk scoring or Stage 5 work is implemented.","","Final class counts: `"+json.dumps(metrics["final_class_counts"],sort_keys=True)+"`. All Stage 1-3.6 protected files were checked unchanged before publishing new artifacts."]
    return "\n".join(lines)+"\n"


def run_pipeline():
    protected=protected_hashes()
    audit,training=read_inputs()
    y=training.weak_label.map(TARGET_MAP).to_numpy()
    pairs=near_pairs(training)
    groups,folds,attempts=choose_folds(training,y,pairs)
    mining_values=pd.to_numeric(training.nearest_mine_or_quarry_distance_km,errors="coerce")
    mining=bool(np.isfinite(mining_values).all() and mining_values.ge(0).all())
    metrics={"evaluation_kind":"spatial out-of-fold weak-label agreement","reference_class_order":CLASSES,"random_forest_configuration":CONFIG,"spatial_configuration_attempts":attempts,"duplicate_control":duplicate_audit(training,pairs),"confidence":{"audit_distribution":audit.confidence.value_counts(dropna=False).to_dict(),"training_distribution":training.confidence.value_counts(dropna=False).to_dict(),"unexpected_audit_values":normalize_confidence(audit.confidence)[1],"unexpected_training_values":normalize_confidence(training.confidence)[1],"categorical_ordinal_mapping":{"l/low":0,"n/nominal":1,"h/high":2}},"mining_alias_included":mining,"versions":{"python":sys.version.split()[0],"scikit_learn":sklearn.__version__,"numpy":np.__version__,"pandas":pd.__version__,"joblib":joblib.__version__},"input_hashes":{p:sha(ROOT/p) for p in ["data/processed/expanded_region_june_audit.csv","data/processed/expanded_region_training_candidates.csv","outputs/expanded_region_readiness.md"]},"models":{}}
    fitted={}; contents={}
    importances={"interpretation":"Impurity importance is not causal explanation; contextual inputs overlap proxy-label sources","random_forest_configuration":CONFIG,"models":{}}
    if folds is not None:
        for name in MODEL_NAMES: metrics["models"][name]=cross_validate(training,y,groups,folds,name,mining)
        metrics["contextual_minus_ablation_macro_f1"]=metrics["models"]["contextual"]["mean_fold_metrics"]["macro_f1"]-metrics["models"]["firms_only"]["mean_fold_metrics"]["macro_f1"]
        decision=go_no_go(metrics["models"]["firms_only"])
        for name in MODEL_NAMES:
            pipeline=make_pipeline(name,mining)
            pipeline.fit(feature_frame(training,name,mining),y)
            fitted[name]=pipeline
            importances["models"][name]={"feature_list":feature_names(name,mining),"importances":parent_importances(pipeline)}
            stream=io.BytesIO(); joblib.dump(pipeline,stream,compress=3)
            contents[f"models/{name}_random_forest.joblib"]=stream.getvalue()
            matrix=metrics["models"][name]["overall_out_of_fold"]["confusion_matrix"]
            table=pd.DataFrame(matrix,index=CLASSES,columns=["predicted_"+c for c in CLASSES]); table.index.name="reference_candidate_class"
            contents[f"outputs/confusion_matrix_{name}.csv"]=table.to_csv(lineterminator="\n").encode()
    else:
        decision=go_no_go({},failures=True)
        metrics["training_stopped_reason"]="No allowed spatial fold configuration feasible; use rules without training either classifier"
    metrics["decision"]=decision
    classified=inference(audit,training,fitted.get("firms_only"),decision)
    metrics["final_class_counts"]={k:int(v) for k,v in classified.predicted_class.value_counts().items()}
    if protected_hashes()!=protected: raise RuntimeError("A protected Stage 1-3.6 file changed; no Stage 4 outputs published")
    contents.update({"data/processed/classified_hotspots.csv":er.lc.csv_text(classified).encode(),"outputs/feature_importances.json":json_bytes(importances),"outputs/classifier_metrics.json":json_bytes(metrics),"outputs/classifier_evaluation.md":evaluation_report(metrics).encode("utf-8")})
    atomic_publish(contents)
    if protected_hashes()!=protected: raise RuntimeError("Protected-file preservation check failed")
    return metrics,{p:hashlib.sha256(b).hexdigest() for p,b in contents.items()}


def main():
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    try:
        metrics,hashes=run_pipeline()
        print(json.dumps({"weak_label_agreement":{n:m["mean_fold_metrics"] for n,m in metrics["models"].items()},"spatial_attempts":metrics["spatial_configuration_attempts"],"decision":metrics["decision"],"final_class_counts":metrics["final_class_counts"],"output_hashes":hashes},indent=2))
    except Exception:
        LOG.exception("Stage 4 validation/training stopped; no silent row removal or threshold change")
        raise


if __name__=="__main__":
    # Persist custom transformer classes under an importable module, never __main__.
    from src.train_classifier import main as entrypoint
    entrypoint()
