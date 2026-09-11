# Fire Monitor: data foundation and Stage 2 features

Python 3.11+; local batch processing. The briefing's classification approach and scope are locked. Stage 1 profiles and normalizes the supplied NOAA-20 VIIRS files. Stage 2 builds observed-date persistence and real Overpass industrial context. No frontend, trained classifier, or final predictions are created.

## Stage 2: exact Windows PowerShell commands

The Stage 1 virtual environment and normalized input already exist:

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
.\.venv\Scripts\python.exe src\build_features.py
.\.venv\Scripts\python.exe -m pytest -q
```

The first feature run needs internet access to the free Overpass endpoint. Subsequent runs validate and reuse the saved real responses. To deliberately obtain a fresh OSM snapshot while retaining previous raw responses:

```powershell
.\.venv\Scripts\python.exe src\build_features.py --refresh-osm
```

Outputs are `data/processed/june_feature_base.csv`, `data/processed/june_feature_audit.csv`, and `outputs/osm_coverage_report.md`; raw responses and manifests are in `data/raw/osm/`. Stage 1 normalized data is never overwritten. Failed requests retry at most three times and fail clearly; inspect the report before using derived outputs. See [feature engineering](docs/feature_engineering.md) for the locked region, 0.01-degree grid, inclusive 30-day formula, WGS84 geodesic-distance method, mining exclusions, and limitations. The audit candidate field contains `true` or `unknown`, with no final labels.

See [Stage 2 validation](docs/stage2_validation.md) for measured results, request outcomes, tests, and reproducibility checks.

## Windows VS Code commands

Open the VS Code integrated **PowerShell** terminal. These commands use the virtual environment directly; activation and execution-policy changes are unnecessary.

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\profile_firms.py
.\.venv\Scripts\python.exe -m pytest -q
```

If `python --version` is below 3.11, select a Python 3.11+ installation before creating the environment. The seven direct dependencies are those requested; pip also installs their dependencies. Stage 1 uses pandas/numpy; Stage 2 also uses GeoPandas, Shapely, requests, and GeoPandas' installed pyproj dependency. Pytest validates both stages. Scikit-learn is reserved for a later stage.

Raw files are already extracted. To reproduce extraction into a fresh checkout:

```powershell
New-Item -ItemType Directory -Force -Path data\raw | Out-Null
Expand-Archive -LiteralPath 'D:\academic_weapon\scripts\DL_FIRE_J1V-C2_803645.zip' -DestinationPath data\raw
```

The original ZIP and briefing at `D:\academic_weapon\scripts` are read-only inputs and are not changed. The Stage 1 profiling script runs offline and never writes to `data/raw`. Running it again replaces only its derived reports and normalized intermediate CSV. Stage 2 separately saves real Overpass responses under `data/raw/osm`.

See [stage-one validation](docs/stage1_validation.md) for measured findings, the commands executed, environment details, and a concrete demo-region candidate. When reading the intermediate with pandas, specify `dtype={"acq_time": "string", "version": "string", "type": "Int64"}` to preserve formatting and nullable metadata.

## Files and data handling

- `src/profile_firms.py`: per-file profiling, validation, and combined normalization.
- `tests/test_pipeline.py`: checks archive precedence, stable identifiers, UTC time formatting, nullable type, invalid-row quarantine, duplicates, and empty input.
- `data/raw/`: original extracted CSVs and supplied readme.
- `data/processed/firms_normalized.csv`: cleaned intermediate records with source filename, source kind, and original CSV line number.
- `outputs/profile_report.json` and `.md`: complete per-file columns, date/coordinate ranges, missing counts, numeric statistics and histograms, categorical distributions, daily detection counts, duplicate counts, schema comparison, and source SHA-256 hashes.
- `outputs/rejected_rows.csv`: normalized rejected records, source references, and reasons; raw values remain in the immutable source CSVs.
- `outputs/duplicate_observations.csv`: removed observation-key duplicates and source references.
- `docs/data_contract.md`: locked future interface containing exactly the 16 requested fields and the feature-importance JSON shape.

All CSV columns are initially read as strings. Dates are ISO UTC dates, acquisition times are zero-padded HHMM strings, numeric features are parsed, `daynight` becomes `day_night`, and VIIRS confidence remains categorical `l/n/h`. `brightness` is retained as supplied. `bright_t31`, scan, track, satellite, instrument, and version remain available as source metadata. `type` is a nullable integer: absent NRT values remain null. It is never inferred from confidence or used as ground truth.

Missing optional measurements remain null without imputation. Invalid coordinates, dates, times, nonfinite or malformed numbers, negative FRP, nonpositive brightness, unsupported instruments, invalid confidence/day-night/type values, or missing sensor identity cause quarantine. Low-confidence records and all valid source types are retained for later explicit filtering; stage one cannot establish sun-glint or artifact status.

Exact raw duplicate counts and observation-key duplicates are reported separately. The observation key is satellite + instrument + exact parsed latitude/longitude + UTC date/time, with no spatial rounding. Archive wins over NRT on the same key; ties use file name and source line. Removed rows remain auditable. Nearby pixels or detections on different dates are not duplicates. SHA-256 of a canonical observation key supplies stable IDs independent of source row ordering. Source file hashes allow later input verification.

The intermediate CSV intentionally differs from the future classified interface: metadata supports audit, while enrichment and predictions do not exist yet. No `classified_hotspots.csv` or `feature_importances.json` is generated. Future evaluation against proxy labels measures agreement with those labels, not verified fire-cause accuracy.

NASA's [FIRMS download readme](https://firms.modaps.eosdis.nasa.gov/download/Readme.txt) identifies J1V as NOAA-20 VIIRS and documents WGS84 coordinates. For this upload, archive/NRT status is preserved from the actual filenames and version fields; generic online availability notes do not override observed file contents.

## Selecting the single demo region and window

Use this dataset to shortlist compact contiguous regions with both repeated activity and transient detections, meaningful FRP variation, and day/night representation. Avoid picking only the highest-FRP event or claiming that dense detections establish industrial activity. Rank candidates by distinct active days and coverage across a candidate 30-day window, not just row totals. A degree-grid shortlist is a screening device only, not the final persistence grid.

Prefer one 30-day demo interval with at least 29 earlier calendar days retained as context for its first day's inclusive trailing 30-day persistence calculation. Do not equate a date without detections with a verified zero-fire observation. Inspect temporal coverage and mark left-censored windows. Decide the exact metric persistence grid and counting semantics in the feature-engineering stage, as required by the contract.

The Stage 1 shortlist was adopted for Stage 2; OSM coverage is now measured in the coverage report. Land-cover coverage and manual review remain future work. No VNF or land-cover downloads have occurred. Detection density alone does not verify industrial versus natural fire examples.

## Stage 3: WorldCover context and readiness evaluation

The statements above describe the earlier stages. Stage 3 adds official ESA WorldCover 2021 v200 context for candidates 15-16 N / 76-77 E and 21-22 N / 72-73 E, June 2026. It evaluates proxy-label coverage and recommends a region only if the fixed readiness thresholds pass. It does not adopt a new scope or train a model. Rasterio is the only additional direct dependency (eight direct dependencies total).

Run these exact commands in the Windows VS Code PowerShell terminal:

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B src\build_landcover_features.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

The first run downloads the official grid and only two required Map COG tiles through unsigned public HTTPS (about 242 MB including the index). Valid downloads are checked and reused under `data/raw/worldcover/v200/`; original Stage 2.5 OSM responses are reused by checksum. No AWS CLI, paid service, API key, Earth Engine or VNF is used. An unavailable/invalid official raster stops the run with a clear error. Do not interpret outputs left from a previous successful run as results of a failed run.

New outputs are the two `data/processed/region_*_landcover_audit.csv` tables, `outputs/landcover_region_comparison.csv`, `outputs/final_region_decision.md`, and the raw WorldCover `manifest.json`. Previous-stage outputs are preserved; these commands do not rerun prior output generators. The `-B` and pytest cache option also avoid rewriting previous bytecode/test caches. Processing is deterministic and contains no changing generation timestamps.

Read the [weak-label specification](docs/weak_label_specification.md), [data provenance](docs/data_sources.md), and [readiness decision](outputs/final_region_decision.md). The centre pixel remains `land_cover_class`; nominal 390 m footprint summaries are audit-only. Industrial/land-cover-derived labels are proxy evidence, not verified causes. Later evaluation must report weak-label agreement and address direct label-source feature leakage. No classifier, `classified_hotspots.csv`, or `feature_importances.json` is produced.

## Stage 3.5: offline extended-window two-class evaluation

Evaluate 21-22 N / 72-73 E for June 1-September 10, 2026, using May onward for each inclusive [date-29, date] persistence window. Stage 3.5 corrects the earlier cropland interpretation to `cropland_hotspot_candidate`: audit context only, with no agricultural-burn class or invented burning-season calendar. Only industrial/wildfire candidates with valid context and complete persistence history are eligible for later training.

Use the existing environment and caches; no dependency installation or external download is required. Run the pipeline and complete test suite twice from the VS Code PowerShell terminal:

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
.\.venv\Scripts\python.exe -B src\build_landcover_features.py --extended
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
Get-FileHash -Algorithm SHA256 -LiteralPath data\processed\region_21_22_72_73_extended_audit.csv, outputs\extended_window_label_distribution.csv, outputs\extended_window_decision.md
.\.venv\Scripts\python.exe -B src\build_landcover_features.py --extended
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
Get-FileHash -Algorithm SHA256 -LiteralPath data\processed\region_21_22_72_73_extended_audit.csv, outputs\extended_window_label_distribution.csv, outputs\extended_window_decision.md
```

The `--extended` flag is required for this stage. It validates local WorldCover files without rewriting the manifest or downloading anything, and permits no OSM network fallback. It writes only the three new extended output files. Earlier-stage outputs remain unchanged. Missing/invalid raster data stops clearly; unavailable OSM context is retained as unknown_context_unavailable and cannot establish a training label. The Stage 3.5 integration tests block Requests and socket connections while regenerating artifacts in memory and checking output bytes against the saved files.

Read [Stage 3.5 methodology correction](docs/stage3_5_methodology_correction.md) and [extended-window decision](outputs/extended_window_decision.md). The 443-row window fails the fixed two-class readiness checks: only 11 wildfire candidates, 97.07% industrial dominance and 90.91% of wildfire candidates in June. **The region/window cannot be locked, and no training should begin under these thresholds.** Cropland remains audit-only; no classifier or final predictions are created.

## Stage 3.6: final expanded-region readiness attempt

Evaluate June 1-30, 2026 in the half-open region 21 <= latitude < 24, 72 <= longitude < 75. Nine one-degree cores use separately cached OSM queries with a 0.02-degree buffer; all distances use the merged deduplicated geometries. The existing N21E072 WorldCover tile is validated and reused. This stage creates proxy-labelled training candidates and a readiness report, without training a classifier.

Run these exact commands in the VS Code PowerShell terminal using the existing environment:

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
.\.venv\Scripts\python.exe -B src\evaluate_expanded_region.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
Get-FileHash -Algorithm SHA256 -LiteralPath data\processed\expanded_region_june_audit.csv, data\processed\expanded_region_training_candidates.csv, outputs\expanded_region_osm_coverage.csv, outputs\expanded_region_readiness.md, data\raw\osm\expanded_region\manifest.json
.\.venv\Scripts\python.exe -B src\evaluate_expanded_region.py --offline
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
Get-FileHash -Algorithm SHA256 -LiteralPath data\processed\expanded_region_june_audit.csv, data\processed\expanded_region_training_candidates.csv, outputs\expanded_region_osm_coverage.csv, outputs\expanded_region_readiness.md, data\raw\osm\expanded_region\manifest.json
```

The first command may acquire missing buffered responses through the free Overpass API; each query has at most three attempts. Prior unbuffered caches are insufficient. Subsequent valid responses are reused, and `--offline` preserves saved failures without new requests. Raw responses and per-cell manifests are under `data/raw/osm/expanded_region/`. Failed cores are context-unavailable, never assumed empty. The real-cache tests block HTTP dispatch and socket connections while reproducing output bytes.

Read the [expanded-region readiness report](outputs/expanded_region_readiness.md) and [classifier feature policy](docs/classifier_feature_policy.md). Only industrial/wildfire proxies with valid measurements, context and complete history enter the training-candidate CSV. Cropland remains audit-only. Direct proxy-source features require weak-label-agreement reporting and a later ablation using only the eight independent FIRMS-derived features. If the nine readiness checks fail, use the pre-agreed rule-based fallback and do not start another region search. No classifier, final prediction file or feature-importance file is created.
