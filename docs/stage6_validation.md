# Stage 6 validation record

## Accepted checkpoint and preservation

Stage 5 was complete and clean on branch checkpoint-stage5-complete when Stage 6 began. The earlier requested checkout start ref checkpoint-stagebefore-stage6 was not present, so that checkout had not occurred. No branch or commit was silently substituted. No commit or push is part of this Stage 6 change.

Before editing, 116 existing files were SHA-256 snapshotted, including source/tests/docs, every prior output, raw files, caches, models, README, requirements and .gitignore. Comparison after implementation found 114 byte-identical protected files; only README.md and requirements.txt changed. The Stage 5 classified source remains exactly `29031a9049f145574c507fba40e6d94b3760052e2d199287d3934d2733b614cf`. All source fields, classifications, risk scores/bands, explanations and null class probabilities remain unchanged. Every export authenticates all five Stage 5 CSV hashes before parsing and checks them again after writing.

## Export results and hashes

Both guarded exports completed with zero network requests, zero classifier imports and identical bytes for all three JSON files. Export reads existing risk values and explanations, not risk-scoring or classifier functions. The compact snapshot contains 674 hotspots, classes industrial=308/wildfire=79/unknown=287, bands critical=0/high=10/moderate=149/low=515, ten high-priority detections and six daily spatial groups. All class_probability values are JSON null. No NaN/Infinity or changing timestamp is serialized. The original 20-row risk distribution is retained in the manifest.

| Tracked JSON file | Bytes | SHA-256, export 1 = export 2 |
| --- | ---: | --- |
| backend/data/demo_hotspots.json | 538571 | `a262f21515dd4e1605d8731876163727e95cfc3772210c875655ddc1109cb3c7` |
| backend/data/demo_alert_groups.json | 4297 | `e9b96cbe3b2b317434b7dfcddd62614144f31a44124a4b81230ec4435b0bd5b7` |
| backend/data/demo_manifest.json | 5575 | `b01ebe4f92f15544ac2ce05262fd29dda5f4fb0012034585831f6c995ea0db68` |

The manifest hash above is computed externally. Its content hashes only the two data JSON files and five source CSVs, never itself. Total JSON size is 548443 bytes. backend/data/.gitattributes fixes LF for exactly these three filenames; git check-attr confirms text=set and eol=lf. This new narrow configuration is necessary to prevent Windows autocrlf checkout conversion from invalidating hashes. Existing .gitignore is unchanged and continues to ignore raw/processed datasets and prior outputs.

## Tests and network validation

The 87 new tests passed before complete-suite validation. They cover source authentication/schema/order, immutable startup data, missing/malformed/changed snapshots, exact counts, export repeatability, all endpoint contracts, scientific filters individually and together, pagination, sorting, empty results, 422/404 responses, ID path safety, GeoJSON coordinates/filter parity, alert ordering/grouping, CORS and isolated backend-only startup. The retained historical suite is also executed without modifications.

First corrected complete-suite run: **337 passed**, 2257 warnings, zero network requests (75.38 seconds). Second complete-suite run: **337 passed**, 2257 warnings, zero network requests (68.41 seconds). Both recorded exactly 63 standard-library asyncio IPC wakeup pairs separately from network requests. No implementation change was needed between the successful runs.

Warnings comprise the 2256 preserved earlier warnings plus Starlette's warning that HTTPX 0.28 remains supported but its TestClient integration is deprecated in favor of HTTPX2. No HTTPX2 dependency was added merely to silence that warning. pip check reports no broken requirements.

Windows asyncio uses a local socketpair wakeup channel. An initial validation wrapper treated nested guard calls for this IPC as outbound requests, causing API test setup failures. The corrected outer wrapper inspects the call stack for exactly socket.py's _fallback_socketpair and a loopback address; every other connect is blocked. Both API-only tests and the corrected complete suite use the same application code. The first corrected full run recorded 63 local asyncio IPC pairs separately from zero network requests. No blocked IPC attempt transmitted a data/API request.

The complete suite runs `.venv/Scripts/python.exe -B` with `pytest.main(['-q','-p','no:cacheprovider'])` inside guards on Requests Session.request, socket connect/create_connection, HTTPX HTTPTransport.handle_request and AsyncHTTPTransport.handle_async_request. HTTPX TestClient uses its in-process ASGI transport, never a network transport. Guard attempts are counted and asserted zero after the suite. The preserved Stage 4 unit tests fit and serialize isolated test fixtures; Stage 6 export and API processes neither import sklearn/joblib nor load or retrain the saved models.

## Startup and endpoint results

Uvicorn started successfully on 127.0.0.1 using an ephemeral local port, loaded 674 records, and shut down cleanly. This check sent no socket-based HTTP requests. Outbound connects were blocked apart from the standard-library asyncio wakeup channel. A fresh process confirmed no sklearn/joblib imports.

All nine endpoints passed in-process tests: /api/v1/health, /meta, /stats, /hotspots, /hotspots/{hotspot_id}, /hotspots.geojson, /alerts, /alert-groups and /risk-distribution. /docs and /openapi.json were also checked. IDs never become paths. Default pagination is 100, maximum 500, with nonnegative offsets; invalid filters/ranges/sorting produce sanitized 422 responses, unknown IDs produce 404, and empty valid results return 200. Default hotspot ordering is date/time/ID ascending; alert ordering exactly follows Stage 5 priority. GeoJSON uses longitude before latitude. Score/group/distribution outputs remain the stored Stage 5 values.

Startup reads three files once into frozen Pydantic records, tuples and a read-only ID index. A test forbids data-file reads while repeatedly requesting every endpoint after startup. Mutating a returned JSON object cannot mutate shared state. CORS permits only localhost:5173 and 127.0.0.1:5173 by default; credentials are false, methods GET/OPTIONS, and unapproved origins receive no allow-origin header. Optional explicit additional origins reject wildcards, paths and embedded credentials.

## Actual Git-tracked isolated checkout

The backend package and three snapshots were staged with git add, not force-added. git ls-files confirms all three JSONs are tracked in the index. git check-ignore -v reports no matching ignore rule. No raw, cache, raster, processed CSV or model-input directory was unignored or staged.

An isolated temporary directory was populated with `git checkout-index` using only the ten tracked backend paths (six Python files, three JSON files and the narrow attributes file). No src/, data/, outputs/ or models/ directory existed in that checkout. All three checked-out hashes matched the originals, including on Windows with autocrlf. A fresh Python process imported that temporary backend, started the application, exercised all nine endpoints via TestClient, and confirmed 674 records, ten alerts, no network requests and no sklearn/joblib/src imports. The existing environment supplied dependencies only. The temporary check shut down and cleaned up without touching project data.

This validates the tracked package's clone/checkout portability once committed. The files are staged for review; they have not been committed or pushed to GitHub by this task.

## Dependencies and file inventory

New direct requirements: fastapi>=0.115,<1; uvicorn>=0.30,<1; httpx>=0.27,<0.29; pydantic>=2.9,<3. Installed versions tested: FastAPI 0.141.1, Uvicorn 0.52.4, HTTPX 0.28.1, Pydantic 2.13.4 and Starlette 1.6.0, on the existing Python 3.14.7 environment. Pydantic v2 is explicitly required for frozen typed contracts. The needed installed distributions and dependencies were available in the user's local Miniconda site-packages and copied byte-for-byte into the venv, with destination hashes checked against local source bytes. No packages or data were downloaded. Existing conda-managed INSTALLER/native-extension RECORD hashes differed from the installed files, so those stale RECORD entries were not represented as upstream integrity verification; actual local source/destination bytes and successful imports/pip check were verified.

Created: backend/__init__.py, backend/app.py, backend/config.py, backend/data_loader.py, backend/filters.py, backend/models.py, backend/data/.gitattributes, the three backend/data/demo_*.json files, src/export_demo_data.py, tests/test_demo_export.py, tests/test_api.py, docs/api_contract.md and this validation record. Modified only README.md for Stage 6 commands/interpretation and requirements.txt for the four required libraries. No services.py forwarding layer, database, authentication, frontend or external alert system was added.

## Presentation and limitations

This API serves a retrospective demonstration dataset. Classes are rule-based weak-label categories, and risk scores rank detections for human review. They are not verified fire causes, probabilities, severity measurements or emergency-dispatch recommendations.

The API is not live and sends no alerts. Persistent routine heat can rank highly; low review priority is not evidence of safety. Sensor geolocation, observation gaps, retrospective same-date persistence, incomplete OSM and static WorldCover context limit interpretation. Grid groups are not incident boundaries. Hashes detect inconsistency, not malicious changes by someone who can also edit code/manifest. FastAPI's browser Swagger UI references CDN assets; the backend and OpenAPI JSON work offline, while a browser may need cached UI assets. No browser/CDN request was made during validation. No visual frontend or Stage 7 work was implemented.
