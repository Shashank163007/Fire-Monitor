# SatBurn frontend — Stage 7

React, TypeScript and React Three Fiber provide a local 3D observation desk for the existing Stage 6 FastAPI snapshot. All work in this stage is confined to `frontend/`. Earlier outputs, Python files, schemas, models and scientific documentation are preserved.

## Start in Windows VS Code

Use Node.js 22.12+ (validated with Node 26.7.0) and the existing Python environment. Dependency installation is a one-time npm operation; runtime makes no external data requests.

In terminal 1, start the existing backend:

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor'
.\.venv\Scripts\python.exe -B -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In terminal 2:

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor\frontend'
npm ci
Copy-Item -LiteralPath '.env.example' -Destination '.env.local'
npm run dev
```

Open **http://127.0.0.1:5173**. The default `VITE_API_BASE_URL=http://127.0.0.1:8000` also works without an environment file. Only a loopback HTTP(S) origin is accepted; credentials, URL paths and external hosts are rejected. This is a local demonstration configuration, not a deployment recipe. The existing backend CORS settings already allow port 5173.

To use the production build, stop the Vite development server first:

```powershell
npm run build
npm run preview
```

The preview uses the same port 5173. All globe outlines, fonts (system fonts), icons, shaders and textures are local. The globe texture is drawn in memory from bundled outlines; it does not fetch map tiles.

## Review flow

1. Confirm **DEMO SNAPSHOT / LOCAL API** and the connection indicator. Region bounds and acquisition dates come from API metadata.
2. Use **Focus region** to inspect the dense hotspot cluster; drag to orbit and scroll to zoom. **Reset view** returns to the full globe.
3. Apply category, priority band, date, day/night, FRP, score, persistence or geographic filters. Active-filter count reflects applied fields, with the bounding box counted as one filter.
4. Hover a marker for its ID, weak-label category, review score, FRP, persistence and acquisition date. Click to focus the camera and fetch the exact detail response.
5. Use the observation index for keyboard navigation, coincident detections and table pagination. Sorting is sent to the API; local table pages do not limit the markers shown.
6. Open the review queue for the complete snapshot's high/critical observations and daily groups. Sort by score or date in either direction. A group opens its representative observation. Selecting an item outside current filters clears those filters so its marker is visible.
7. Read **Methodology** for scientific limitations. Escape closes the modal and restores focus. Reduced-motion preferences disable camera interpolation and decorative transitions.

Global summary cards, risk distribution and the review queue describe the **full snapshot**, not filtered matches. Globe and observation index show the filtered subset. Missing values display **Not available**; null model probability is never displayed as a prediction.

## API and query handling

The centralized client in `src/api/client.ts` calls only these unchanged endpoints:

- `/api/v1/health`, `/api/v1/meta`, `/api/v1/stats`
- `/api/v1/hotspots`, `/api/v1/hotspots/{hotspot_id}`, `/api/v1/hotspots.geojson`
- `/api/v1/alerts`, `/api/v1/alert-groups`, `/api/v1/risk-distribution`

Every response is parsed with a runtime Zod schema and inferred TypeScript type. All result pages are fetched with `limit=500` and advancing `offset`, retaining supported sort/filter parameters. Stalled or inconsistent pagination, duplicate IDs, unexpected probabilities and mismatched hotspot/GeoJSON coordinates fail visibly. No production data is embedded in frontend source. Tests read the existing tracked snapshot as fixtures.

The API supports `min_persistence` but no maximum persistence parameter. The maximum is therefore applied locally **after all matching server pages have loaded**, consistently to the globe and index. Unsupported query parameters are never sent. Bounding-box order is west,south,east,north, matching the existing API. No score, class or persistence value is recalculated.

Requests use GET, omit credentials, reject redirects and time out after 15 seconds. Query changes abort obsolete requests. A 15-second health check detects backend loss; any context-loading failure hides prior data and exposes an explicit retry state. Detection of a silent network timeout can take the health interval plus request timeout (up to approximately 30 seconds). There is no fallback JSON import, offline fabricated dataset, model loader or external alert transmission.

## Visual and scientific interpretation

The globe uses two instanced draws for marker discs and priority rings. Coordinates use
`x = r cos(latitude) cos(longitude)`,
`y = r sin(latitude)`,
`z = -r cos(latitude) sin(longitude)`.
Marker size adapts for legibility and is not a physical footprint or intensity measurement.

API values `industrial`, `wildfire` and `unknown` are preserved. UI labels are **Industrial candidate**, **Wildfire candidate** and **Unknown**, meaning rule-based weak-label context. Orange, red and grey encode those categories. Rings encode the supplied priority band. Neither colors nor rings establish fire cause or severity.

Scores are unchanged deterministic human-review priorities, not probabilities, severity measurements, verified causes or dispatch recommendations. Sensor confidence remains distinct from model probability. OSM is incomplete; WorldCover 2021 v200 is static context for 2026 observations. Coarse FIRMS geolocation, approximate footprint/grid sizes and coincident points limit spatial interpretation. Daily groups are not incident boundaries. No classifier is operational.

## Validation commands

```powershell
Set-Location 'D:\academic_weapon\vscode\SIH26162\fire-monitor\frontend'
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
```

The browser test requires installed Google Chrome, uses its headless WebGL renderer and starts temporary local API/preview servers itself. Stop manually started servers on ports 8000 and 5173 before running it. It never downloads a browser. It blocks and records any request outside the local app/API origins, uses the actual Stage 6 snapshot, and exercises filters, page loading, selection, alerts, tablet layout, reduced motion and offline recovery. Screenshots, traces and machine-readable results are generated under ignored `test-results/`.

See [VALIDATION.md](VALIDATION.md) for the completed checks and exact file inventory.

## Attribution and dependency sources

[Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) reference cartography is public-domain data. The local [world-atlas](https://github.com/topojson/world-atlas) package redistributes Natural Earth 4.1.0 as TopoJSON; this frontend bundles `countries-110m.json` (1:110m scale), not precision regional mapping. World Atlas is copyright 2013–2019 Michael Bostock, ISC licensed; the full notice is included in `public/world-atlas-LICENSE.txt` and copied into the production build.

The stack uses free/open-source packages: [Vite](https://vite.dev/guide/), React, Three.js, React Three Fiber, drei, Framer Motion, Lucide, Zod and TopoJSON. Exact package versions are recorded in `package.json` and `package-lock.json`. No paid service, API key or billing account is needed. Natural Earth outlines are solely visual reference; all scientific measurements still come from the local API.

Stage 7 stops at the frontend. It adds no ingestion, classifier training/serving, alert delivery or Stage 8 integration.
