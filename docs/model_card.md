# Stage 4 binary weak-label Random Forest model card

## Intended use and fixed scope

This local batch prototype measures **weak-label agreement** for industrial versus wildfire candidate classes. It does not establish verified fire cause. Region: 21 <= latitude < 24, 72 <= longitude < 75; target dates June 1-30, 2026. Stage 3.6 is accepted: 674 audit rows comprise 308 industrial, 79 wildfire, 208 cropland-context and 79 unknown proxies. Exactly 387 rows, 308 industrial_candidate and 79 wildfire_candidate, enter training. No row balancing, oversampling, SMOTE, synthesis or silent removal is permitted.

The binary reference mapping is industrial_candidate -> industrial and wildfire_candidate -> wildfire. Other rows remain unknown in the classified output. These labels come from the preserved Stage 3.6 rules, not verified incidents. Cropland context is never called agricultural burning. No flare class is trained.

## Input validation and preserved provenance

The pipeline validates exact locked counts, unique nonmissing IDs, schemas, June dates, half-open coordinates, HHMM times, conflict exclusion, complete history, FIRMS validity flags, OSM query/distance validity and WorldCover code/name/status consistency. The training table must equal its eligible audit subset. The Stage 3.6 readiness decision is parsed and compared with a recalculation; any mismatch stops processing rather than changing thresholds or rows. The three input file hashes appear in classifier_metrics.json.

All Stage 1-3.6 source files, raw inputs, cached responses, processed outputs, reports and tests are preserved. No external data are acquired. README.md is the only existing file intentionally modified, solely to append Stage 4 execution and model-loading instructions. No additional dependency is needed: scikit-learn and its joblib dependency are already installed. Model pipelines are serialized with the importable src.train_classifier.FeatureCleaner class, not a nonportable __main__ class.

## Two separate feature sets

Model B, the mandatory FIRMS-only ablation, uses exactly frp, brightness, bright_t31, confidence, day_night, persistence_count_30d, scan and track. Model A adds distance_to_industrial_km, land_cover_class, and distance_to_mining_km when finite/nonnegative values exist for all eligible rows. The last field is an explicitly documented alias of Stage 3.6 nearest_mine_or_quarry_distance_km.

The feature matrix excludes hotspot IDs, raw coordinates, cell/region identifiers, dates/times, weak labels, reference targets, reasons, conflict/eligibility/query flags, predicted outputs, risk values and footprint-derived context. Labels and coordinates are used only outside the matrix for reference outcomes and grouping. Numeric land_cover_code is not added alongside its categorical name.

Model A overlaps the direct sources used to construct weak labels, so its agreement can reflect label-source leakage. Its result is diagnostic and cannot authorize classifier deployment. Model B excludes those contextual sources but still predicts imperfect proxies. Neither model's score is verified real-world fire-cause performance. A large contextual advantage indicates possible dependence on the same contextual evidence used to create labels.

## Confidence and fold-local preprocessing

Observed training confidence: n=343, l=43, h=1; audit confidence: n=575, l=96, h=3. The explicitly chosen ordinal representation is l/low=0, n/nominal=1, h/high=2. These are ordered categories, not probabilities or percent confidence. Finite numeric confidence in [0,100] is preserved numerically; unexpected strings, nonfinite numbers and out-of-range numbers become missing, with counts reported. Numeric and ordinal scales are not interchangeable; mixed-scale future data need review, although all actual accepted values here are categorical.

Each newly constructed Pipeline contains stateless feature normalization, a ColumnTransformer, and a Random Forest. Numeric parsing invalidates nonfinite values, negative FRP/distances/persistence and nonpositive temperatures/pixel dimensions; missing values receive training-fold median imputation. Categorical strings are stripped and lowercased, blank values become missing, most-frequent imputation is learned in the training fold, and OneHotEncoder ignores unseen validation categories. Imputers retain empty feature positions. No encoder or imputer is fitted to all 387 rows before cross-validation.

## Spatial evaluation and repeat control

Initial spatial groups use Decimal floor-based globally anchored 0.1-degree bins. Groups linked by any coordinate pair within 390 m on the WGS84 ellipsoid are conservatively merged, across all dates, to keep near-repeat source observations together even across grid edges. This nominal VIIRS-scale threshold is a reproducibility choice, not proof of duplicate identity or a measured footprint. Connected chains can enlarge groups. Temporal observations are retained.

Duplicate reporting includes repeated IDs, exact observation keys (coordinates, acquisition date/time, satellite and instrument), duplicate coordinates and likely same-overpass pairs within 390 m and 60 seconds. Identical IDs fail validation; exact or likely duplicate observations otherwise remain grouped, without deleting legitimate recurrence observations.

The fixed fallback sequence is (0.1 degree, 5 folds), (0.1 degree, 3), (0.05 degree, 5), (0.05 degree, 3), using StratifiedGroupKFold with shuffle=True and random_state=26162. Every attempted configuration and rejection reason is recorded. No smaller grid, alternate seed or random row split is allowed. Before fitting, training/validation must share no group or near pair; both classes must occur with at least two observations per class in each partition. The two-row minimum is the predeclared meaning of enough rows for nondegenerate metrics. Rejection describes the allowed fixed-seed partition, not proof that every combinatorial split is impossible. If no configuration works, stop classifier training and use the rule fallback.

Per-fold and pooled out-of-fold metrics include confusion matrices (reference rows, predicted columns; class order industrial, wildfire), per-class precision/recall/F1/support, macro and weighted F1, balanced accuracy against proxy references, and wildfire-positive ROC-AUC when both reference classes are present. Fold row counts, class distributions, group counts and leakage checks are recorded. The go/no-go gate uses unweighted means of fold macro F1 and wildfire recall, not pooled metrics or ordinary accuracy. Fold sizes can differ substantially because persistent sources must stay together.

## Fixed models and operational gate

Both RandomForestClassifier instances use n_estimators=400, class_weight=balanced, random_state=26162, n_jobs=-1, min_samples_leaf=2 and max_features=sqrt. Other sklearn defaults are unmodified. No hyperparameter tuning against these folds occurs. Training uses all CPU workers; raw predict_proba uses temporarily serial tree accumulation to stabilize floating-point order, then n_jobs=-1 is restored before serialization. This changes scheduling only, not probabilities, trees, calibration or model selection.

The operational classifier is Model B only if it has at least three valid spatial folds, no shared groups, both classes in every validation fold, mean macro F1 >=0.75, mean wildfire recall >=0.60, and no validation/pipeline/metric failures. A high Model A score cannot rescue a failing Model B. If the gate fails, the operational prototype uses the existing rule-based weak-label method. Thresholds are not adjusted to the result.

Only after cross-validation completes are both pipelines fitted on all 387 eligible observations and saved as models/contextual_random_forest.joblib and models/firms_only_random_forest.joblib. These final fits do not supply evaluation metrics. Their eligible-row inference is in-sample batch output; generalization evidence comes only from held-out spatial folds.

## Stage 4 output interface and explicit revisions

classified_hotspots.csv has exactly the 16 fields requested in Stage 4 and 674 uniquely identified rows, ordered by acquisition date/time, latitude, longitude, satellite and hotspot ID. Satellite is used for sorting but omitted from the 16-field interface. Raw source confidence and zero-padded times are preserved.

When Model B passes, eligible rows receive industrial/wildfire predictions and the maximum raw uncalibrated predict_proba value. Non-eligible rows always remain unknown with null probability. When rules are operational, eligible candidate classes are preserved as industrial/wildfire, other rows are unknown, and every probability is null. Random Forest confidence is not a verified real-world probability. No fabricated probabilities or risk values are allowed; risk_score and risk_band remain null pending Stage 5.

The current Stage 4 instruction explicitly changes the historical predicted-class enum to industrial/wildfire/unknown and requests contextual/FIRMS-only feature-importance lists separately with configuration and feature metadata. These current instructions supersede the older enum/list examples in docs/data_contract.md; that historical file is intentionally preserved. outputs/feature_importances.json contains a models object with contextual and firms_only entries, each holding feature_list and a descending importances list of {feature, importance}. The top level includes configuration and interpretation. One-hot importances are summed back to parent features; each model sums approximately to one. Impurity importance reflects the fitted splits, not causal explanation. No SHAP values are generated.

## Limitations and prohibited uses

The region/month and wildfire sample are small and selected using contextual proxy availability. Grouping reduces local repeat leakage but does not establish independent fire events or remove larger spatial correlations. The split is not a prospective temporal experiment. The locked persistence feature is retrospective through the acquisition DATE, including later same-day detections; it must not be marketed as an acquisition-time live feature. No observations after the acquisition date enter that persistence window.

OSM is a later static mapping snapshot, not necessarily June infrastructure state, and WorldCover 2021 may not match 2026 cover. These timing limitations reinforce that contextual Model A is diagnostic only. The independent ablation uses FIRMS-derived features, not future event outcomes. Geolocation uncertainty, unmapped mining, non-combustion industrial tags, coincident burning, observation gaps and weak-label selection bias remain. Neither result validates real fire causes. The scores must be described as weak-label agreement.

No risk scoring, alert system, frontend or Stage 5 work is included. Only load joblib artifacts generated by this trusted local project; model loading reconstructs Python objects.

Measured results, fold assignments, selected operational method and hashes are recorded in outputs/classifier_metrics.json and outputs/classifier_evaluation.md. Validation results are recorded in docs/stage4_code_review.md.

## Measured operational status

**Classifier no-go: retain the rule-based weak-label fallback.** The accepted 0.1-degree, five-fold split has 92 merged spatial groups. Mean fold macro F1 is 0.994647 for the contextual model and 0.609705 for FIRMS-only, a gap of 0.384942. FIRMS-only wildfire recall is 0.846667, but its macro F1 misses the fixed 0.75 threshold. Contextual agreement cannot rescue this failure because context helped generate the labels. No thresholds or parameters were adjusted.

Both models are saved for reproducible inspection, not selected as the operational classifier. The final interface uses rule-based industrial (308), wildfire (79) and unknown (287) values; all probabilities and risk values are null. The full suite passed 170 tests. Two complete offline pipeline runs made zero network attempts and produced identical required CSV/JSON hashes and operational decisions. See stage4_code_review.md for the measured validation and preservation evidence.
