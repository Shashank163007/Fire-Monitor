# Stage 4 implementation review

This review covers the new binary proxy-label classifier. Existing Stage 1-3.6 artifacts and tests remain preserved. The only existing-file change is appending README.md instructions so the user can run Stage 4, locate its outputs and load the saved pipelines. requirements.txt remains unchanged because all dependencies, including joblib through scikit-learn, are installed.

## Data and feature boundaries

Input validation stops on any mismatch in the locked 674/387 counts, class distribution, schemas, unique IDs, scope, conflicts, valid context, eligible-audit equality or Stage 3.6 readiness result. No rows are silently dropped. Inputs are read from the preserved Stage 3.6 CSVs and report; no network operation or data-refresh function is called.

Feature construction uses explicit model-specific allowlists, with a transformer check rejecting missing/extra matrix columns. The binary target is supplied separately to fit. Contextual nearest_mine_or_quarry_distance_km is deliberately aliased to distance_to_mining_km and is absent from the ablation. Target, IDs, coordinates, date/cell fields, proxy-derived audit fields and risk/prediction outputs never enter the matrices. Confidence normalization is stateless; all learned imputation and category encoding are inside fold-specific pipelines.

## Split integrity and evaluation

Spatial bins use decimal floor arithmetic. Near-coordinate pairs within 390 m merge grid groups before any split, including temporal repeats and cross-boundary observations. Duplicate observations are reported rather than removed. The four allowed configurations are tried in the exact requested order; rejection reasons are retained. Both models use identical accepted folds and fixed hyperparameters. Fold generators validate group and near-pair exclusivity before any forest is fitted.

Each fold constructs a fresh Pipeline; only its training partition fits preprocessing and forest parameters. Validation probabilities are raw model outputs. Pooled OOF predictions cover each eligible observation once. Class-specific metrics explicitly use industrial/wildfire order; ROC-AUC treats wildfire as positive and returns null if undefined. Ordinary accuracy is not the headline metric. The gate reads only the FIRMS-only fold means and explicit leakage/failure checks.

## Final fit, outputs and reproducibility

Final fits happen only after cross-validation for both models. Model A is diagnostic; the fixed operational choice is Model B on a passing gate, otherwise rules. Non-eligible rows remain unknown regardless of model predictions. Rule fallback assigns no probability. Output validation enforces 674 unique nonmissing IDs, the exact 16 fields, permitted classes, probability ranges/nulls and empty risk columns.

Random Forest fitting retains n_jobs=-1. Prediction temporarily uses n_jobs=1 to make accumulation order deterministic, then restores the required configuration. Serialized transformer references use src.train_classifier, so joblib loading works outside the training script. Feature importances are real impurity importances aggregated by ColumnTransformer/OneHotEncoder parent mapping, checked for total one and sorted deterministically.

Every output is fully computed before publishing. Each file uses a same-directory temporary file, flush/fsync, then os.replace for an atomic replacement. This is atomic per file, not a multi-file transaction; interruption during publishing may leave a mixture of complete versions, so rerun and verify hashes before downstream use. Earlier-stage hashes are checked before and after publishing. Generation timestamps and wall-clock durations do not enter deterministic outputs.

## Contract interpretation and remaining risks

The Stage 4 request explicitly authorizes unknown in the classified interface and separate contextual/ablation importance lists with metadata. This supersedes those two older examples without editing the historical contract. The row count and exact 16-field order are retained.

The nominal 390 m grouping rule is conservative, not proof of duplicate identity. Large persistent groups can make fold sizes unequal, and two observations farther apart than 390 m can still belong to one physical source. Spatial folds do not establish temporal generalization. Model A uses label-source context and later/static source snapshots; only the FIRMS-only ablation can pass the operational gate. Existing daily persistence remains retrospective, not live at observation time. Raw probabilities are uncalibrated. All reported classification metrics compare with weak labels, not independently verified causes.

Unit and integration tests cover validation failures, target mapping, both feature sets, mixed confidence, train-only preprocessing, exclusive deterministic grouping, near duplicates, forbidden fallbacks, metric arithmetic, operational thresholds, probability/null behavior, 674-row schema, importance aggregation, seed reproducibility, portable serialization and atomic writes. The full earlier-stage suite is retained and executed as part of Stage 4 validation.

## Completed validation and measured decision

The complete suite passed: **170 tests**, including 29 new Stage 4 tests. The full invocation used `.\.venv\Scripts\python.exe -B` with `pytest.main(['-q', '-p', 'no:cacheprovider'])` inside a network guard. The guard replaced `requests.sessions.Session.request`, `socket.socket.connect` and `socket.create_connection` with a function that records and raises on any attempt; its attempt count was zero. The 2,256 warnings comprise existing upstream warnings and the intentional undefined/single-class metric test warning; no test failed.

After the suite, the Stage 4 pipeline completed twice under the same network guard, each invoking `src.train_classifier.main()`. Both recorded zero network attempts. An initial restricted Windows execution was blocked while creating the local worker-pool IPC handle, before the first forest fit. Granting local execution permission resolved that environment error; the two completed runs had no pipeline, metric or validation failures. No model parameter, fold, seed or gate threshold was changed in response.

The preferred 0.1-degree grid with five folds was accepted immediately: 92 spatial groups after conservative 390 m merging. Validation fold sizes were 193, 75, 39, 41 and 39. All folds contained both classes, shared no group with their training partition, and divided none of the 4,084 nearby coordinate pairs. Of those pairs, 98 were possible same-overpass repeats within 60 seconds. There were zero repeated IDs, exact observation duplicates or exact coordinate duplicates; no rows were removed. Both models used the same folds and fold-local preprocessing.

These are unweighted means across the five spatial folds, measured against proxy references:

| Model | Macro F1 | Wildfire recall | Balanced accuracy against weak labels | ROC-AUC |
| --- | ---: | ---: | ---: | ---: |
| Contextual | 0.994647 | 0.987500 | 0.993750 | 1.000000 |
| FIRMS-only | 0.609705 | 0.846667 | 0.687467 | 0.755047 |

The macro F1 gap is 0.384942. Model A's label-source overlap can explain its advantage; it cannot authorize deployment. Model B fails the unchanged mean macro F1 threshold of 0.75. Every other gate condition passes. **The operational method is rule_based_weak_label_fallback.** Both final models were still fitted on all 387 eligible rows and saved as requested. The 674-row classified interface contains 308 industrial, 79 wildfire and 287 unknown rows, preserving rules rather than classifier predictions. Every class_probability, risk_score and risk_band is null.

Both saved pipelines were loaded in a fresh Python process. Their required forest parameters, probability shape/sums and parent-importance totals were checked. The saved CSV was independently checked for its exact 16 columns, 674 unique IDs, deterministic order, null outputs and equality of its 12 source fields with the accepted audit table.

## Deterministic hashes and preservation

The following SHA-256 values were identical in both complete runs; the operational decision also matched exactly:

| File | SHA-256, run 1 = run 2 |
| --- | --- |
| data/processed/classified_hotspots.csv | `b5d0840a9e8f0865fc6d1972c23e21b98a8294efcf5e5453cb5b443b3314373f` |
| outputs/classifier_metrics.json | `85846b6dab215fbf7ad9799465fc4c732050592d3ab4ca1b21012964aab63a06` |
| outputs/feature_importances.json | `74f90f36bf7c7082e43c7f50bb27b9f36ab5d34e2e5b5d537c2df5e8fad43053` |

Both model binaries, both confusion matrices and classifier_evaluation.md also had matching hashes across the two runs. Comparing the 94 pre-existing files snapshotted before Stage 4 showed 93 byte-identical files and only the authorized README.md modification. requirements.txt, all prior source/tests/docs, Stage 1-3.6 reports and datasets, and raw/OSM/WorldCover caches were unchanged; no protected file was added or removed.

New Stage 4 files: src/train_classifier.py; tests/test_classifier.py; models/contextual_random_forest.joblib; models/firms_only_random_forest.joblib; data/processed/classified_hotspots.csv; outputs/feature_importances.json; outputs/classifier_metrics.json; outputs/classifier_evaluation.md; outputs/confusion_matrix_contextual.csv; outputs/confusion_matrix_firms_only.csv; docs/model_card.md; docs/stage4_code_review.md. README.md is the sole modified existing file. No risk scoring, alerts, frontend or Stage 5 implementation was created.
