# Stage-one validation results

Executed locally on 2026-09-11 using Python 3.14.7. The complete briefing was read before implementation; the user's stage-one request limits the broader plan to ingestion and profiling.

| Finding | Archive | NRT |
| --- | --- | --- |
| Rows | 85,045 | 24,721 |
| Columns | 15 | 14 |
| UTC dates | 2026-05-01 to 2026-05-31 | 2026-06-01 to 2026-09-10 |
| Latitude min / max | 8.16141 / 34.57174 | 8.17020 / 34.47789 |
| Longitude min / max | 68.57764 / 96.64244 | 68.56112 / 96.92564 |
| FRP min / median / max | 0.11 / 4.44 / 451.36 | 0.15 / 3.33 / 348.59 |
| Brightness min / median / max | 207.93 / 338.26 / 367.00 | 207.93 / 333.33 / 367.00 |
| Confidence l / n / h | 22,382 / 60,806 / 1,857 | 2,101 / 22,411 / 209 |
| Day / night | 67,753 / 17,292 | 15,268 / 9,453 |
| Missing values in supplied columns | 0 | 0 |
| Exact duplicates | 0 | 0 |
| Observation-key duplicates | 0 | 0 |

Common columns: `latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite, instrument, confidence, version, bright_t31, frp, daynight`.

Archive-only column: `type`, with 78,051 values of 0, 6,914 values of 2, and 80 values of 3. NRT has no `type` column. Both files contain satellite `N20`, instrument `VIIRS`; versions are `2` and `2.0NRT`, respectively. No unsupported field-name aliases were needed for this upload.

The combined intermediate has **109,766 rows**, zero rejected rows, zero duplicates removed, and 24,721 null `type` values. No other intermediate values are missing. IDs are unique, and all acquisition times retain four digits. Both sources have detections on every calendar date within their respective file ranges; this does not prove complete satellite observation coverage in any region.

All three extracted files were compared byte-for-byte against ZIP members and matched. Original ZIP SHA-256:

```text
284192fcf4281b66bd6179aecd11ef114caf194d5f21b084b4f41f882118e2f7
```

## Region and time-window recommendation

Monthly row counts are May 85,045; June 17,954; July 2,576; August 2,470; September 1-10 1,721. This temporal imbalance makes full-period density alone a poor selection criterion.

For a first candidate, inspect the bounding box **23 <= latitude < 24, 86 <= longitude < 87**, with **June 1-30, 2026** as the demo interval and May retained as historical context. Local screening found 2,663 detections over 100 distinct days across the full dataset in this box. During June it has 736 detections across 25 dates, 158 daytime and 578 nighttime detections, and median FRP 2.545. Confidence is 689 nominal and 47 low; no high-confidence detections occur in that candidate interval. These are detection statistics, not evidence of industrial fire causes.

Compare this candidate with other compact regions using active days, recurring versus transient locations, FRP variation, and day/night balance. Choose one only after later industrial and land-cover coverage checks and visual spot checks. Retain at least the preceding 29 days for an inclusive daily trailing 30-day persistence feature. The current one-degree screening boxes do not define the future persistence grid, and this stage does not compute persistence or select proxy labels.

## Commands executed

Project creation and extraction from the workspace root:

```powershell
Get-Content -LiteralPath 'D:\academic_weapon\scripts\hackathon_context_briefing.md' -Raw
New-Item -ItemType Directory -Force -Path fire-monitor/data/raw,fire-monitor/data/processed,fire-monitor/outputs,fire-monitor/src,fire-monitor/tests,fire-monitor/docs | Out-Null
Expand-Archive -LiteralPath 'D:\academic_weapon\scripts\DL_FIRE_J1V-C2_803645.zip' -DestinationPath 'fire-monitor/data/raw'
Get-Content fire-monitor/data/raw/Readme.txt
Get-Content fire-monitor/data/raw/fire_archive_J1V-C2_803645.csv -TotalCount 4
Get-Content fire-monitor/data/raw/fire_nrt_J1V-C2_803645.csv -TotalCount 4
python --version
```

The following commands ran with `fire-monitor` as working directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\profile_firms.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -c "import faulthandler; faulthandler.dump_traceback_later(10); import pandas; print(pandas.__version__)"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q
```

The first environment creation and installation attempts hit sandbox temporary-file/package-access restrictions; authorized retries succeeded. Initial tests passed with a cache warning; a cache-disabled retry encountered the inaccessible temporary cache directory during collection. `pytest.ini` now scopes collection to `tests`, and the final authorized run completed **4 passed in 0.46s**, without warnings. The profiling command completed successfully on the first full dataset run. A preliminary `py -0p` probe found no Windows Python launcher, so documented commands use `python`.

Additional read-only Python checks used PowerShell here-strings piped to `.\.venv\Scripts\python.exe -` to summarize reports and screen regions. The final integrity and candidate check was:

```powershell
@'
import hashlib
import zipfile
from pathlib import Path
import pandas as pd
archive = Path(r'D:\academic_weapon\scripts\DL_FIRE_J1V-C2_803645.zip')
with zipfile.ZipFile(archive) as z:
    for member in z.namelist():
        assert z.read(member) == (Path('data/raw') / member).read_bytes(), member
print('All three extracted files match ZIP contents byte-for-byte.')
print('ZIP SHA256:', hashlib.sha256(archive.read_bytes()).hexdigest())
df = pd.read_csv('data/processed/firms_normalized.csv', dtype={'hotspot_id': 'string', 'acq_time': 'string', 'version': 'string', 'type': 'Int64'})
roi = df[df.latitude.between(23, 24, inclusive='left') & df.longitude.between(86, 87, inclusive='left') & df.acq_date.between('2026-06-01', '2026-06-30')]
print('Candidate 23-24N, 86-87E, June 1-30:', len(roi), 'rows;', roi.acq_date.nunique(), 'active days;', roi.day_night.value_counts().to_dict())
print('Candidate confidence:', roi.confidence.value_counts().to_dict(), 'FRP median:', roi.frp.median())
print('Normalized ID uniqueness:', df.hotspot_id.is_unique, 'four-digit acquisition times:', df.acq_time.str.fullmatch(r'[0-9]{4}').all())
'@ | .\.venv\Scripts\python.exe -
```

Direct installed dependency versions: pandas 3.0.5, numpy 2.5.3, scikit-learn 1.9.1, geopandas 1.1.4, shapely 2.1.2, requests 2.34.2, pytest 9.1.1. Requirements use lower bounds for Python 3.11+ compatibility; this execution validates the listed environment, not every Python version.
