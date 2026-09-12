# Stage 5 deterministic review-priority specification

This deterministic score ranks FIRMS thermal detections for human review. It is not a probability, verified severity measurement, fire-cause determination or emergency-dispatch recommendation.

## Scope and source authentication

The accepted scope is 21 <= latitude < 24, 72 <= longitude < 75, June 1-30, 2026. Exactly 674 unique hotspots retain 308 industrial, 79 wildfire and 287 unknown rule-based context categories. Stage 4's FIRMS-only classifier failed its operational gate; both saved models remain evaluation artifacts. Stage 5 neither loads nor invokes them, imports the training script, retrains a classifier, downloads data nor transmits alerts. Model file bytes may be hashed solely to verify preservation.

The required original Stage 4 input SHA-256 is `b5d0840a9e8f0865fc6d1972c23e21b98a8294efcf5e5453cb5b443b3314373f`. Initial probability/score/band fields must be empty. All 16 columns and their order must match the Stage 4 contract. IDs, all first 14 source columns, original string representations and row order are immutable. No row is removed, reordered or relabelled. A failed hash, count, scope, schema, FRP or persistence check stops execution before publishing.

For a scored rerun, ONLY risk_score and risk_band are cleared in memory; serializing that table as UTF-8, comma-separated CSV with LF endings must reproduce the original Stage 4 hash exactly. Every existing score and band must also equal a fresh deterministic calculation, including the canonical two-decimal score representation. Partial scores or mismatches stop, rather than being repaired. No backup data file, model inference or reconstructed label rule is used. The input hash is logged before the first write and recorded in the validation report.

## Exact formula and fixed weights

Only FRP, the existing persistence count, confidence and day/night affect the score:

```text
F <= 5:          frp_points = 0
5 < F <= 20:     frp_points = ((F - 5) / 15) * 10
20 < F <= 50:    frp_points = 10 + ((F - 20) / 30) * 15
50 < F <= 100:   frp_points = 25 + ((F - 50) / 50) * 10
F > 100:        frp_points = 35 + min((F - 100) / 100, 1) * 5
frp_points = clamp(frp_points, 0, 40)

persistence_points = clamp(((persistence_count_30d - 1) / 29) * 30, 0, 30)

numeric confidence in [0,100]: confidence_points = clamp(confidence / 100, 0, 1) * 20
low or l: 5 points; nominal or n: 12 points; high or h: 20 points
confidence_points = clamp(confidence_points, 0, 20)

N or night: night_points = 10
D or day:   night_points = 0
night_points = clamp(night_points, 0, 10)

risk_score = round(clamp(frp_points + persistence_points + confidence_points + night_points, 0, 100), 2)
```

FRP is in MW, finite and nonnegative. Its continuous monotone function gives 0 at <=5 MW, 10 at 20, 25 at 50, 35 at 100 and 40 at >=200. It receives the largest weight (40) to prioritize measured thermal intensity, without interpreting it as damage. Persistence receives 30 points to prioritize recurring detections; one active date gives zero and 30 gives 30. Confidence receives 20 to reflect sensor detection confidence, not confidence in a class or severity. Night observations receive 10 to prioritize continued thermal activity visible at night, not to establish industrial origin or greater danger. These weights are user-prescribed review policy, not estimated parameters or calibrated incident thresholds.

The existing persistence_count_30d is validated as an integer in [1,30] and is never recalculated. It counts distinct acquisition dates in the same fixed 0.01-degree cell within inclusive [date-29,date]. Multiple detections on a date count once. It is a retrospective daily measure, including later observations on the same date; Stage 5 does not acquire or add future information. This is not an acquisition-time live score. Thirty available calendar dates do not guarantee clear-sky observations every day.

## Confidence and day/night normalization

Actual accepted confidence values are n=575, l=96, h=3. Normalize whitespace and case; audit categories are nominal, low and high. Actual day/night values are D=510 and N=164; audit values are day/night. Numeric sensor confidence is accepted only if finite and in [0,100]; out-of-range or nonfinite values are unexpected, not clipped into apparent valid sensor confidence. Unexpected or missing confidence receives zero points and audit value unknown. Count missing and unexpected values separately. The accepted data have zero such values.

Stage 4 maps low/nominal/high to 0/1/2 solely as ordered classifier input encodings. Those numbers are not risk points, percentages or normalized sensor confidence. Stage 5 reads the unchanged raw l/n/h column and maps it directly to the user-prescribed 5/12/20 review points; it never consumes or rescales Stage 4's encoded values. There is no existing risk-point mapping to conflict with this one. The Stage 4 metadata mapping is checked explicitly; any change requires review and stops execution. Historical mappings and tests remain untouched.

Missing or unexpected day/night receives zero points and audit value unknown, with separate counts, as expressly required by the Stage 5 night-component rule. Only documented aliases are mapped to day/night; unknown is an audit sentinel, never a guessed observation category. This applies the explicit zero-and-report rule to the general input-validation requirement; all 674 accepted values are documented and valid. FRP, persistence, scope, identity and probability problems remain critical errors. The validation report records all encountered categories and invalid/missing counts.

## Excluded scoring information

Predicted class, class_probability, industrial/mining distances, land cover, coordinates, IDs, OSM counts and classifier outputs never enter the four-argument numeric scoring function. Class appears only as descriptive rule-based context in explanations and aggregate counts. Thus identical permitted score inputs always receive identical points across classes, including unknown rows. Context and class are excluded to avoid treating proxy cause evidence as severity or double-counting the evidence used to assign weak labels.

Brightness and bright_t31 are excluded because this score explicitly uses FRP as its sole thermal-intensity input; adding brightness would introduce a second thermal measurement and an unrequested weight. No dataset percentiles, sample-relative normalization, randomness or fitted model is used. Fixed physical-unit breakpoints keep the same input values at the same priority when the dataset changes.

## Bands, explanations and precision

Use the rounded final score: critical >=75; high >=55 and <75; moderate >=35 and <55; low <35. Every row receives exactly one lowercase band. These names designate prototype review priority only.

The primary driver is the highest unrounded component contribution. Exact ties select thermal_intensity, then persistence, observation_confidence, night_observation. An all-zero tie selects thermal_intensity without claiming elevated FRP. Fixed explanation templates identify the primary driver and report the four component contributions, followed by `Rule-based context category: ...`. High sensor confidence is stated only for the high category. These deterministic contribution explanations do not use model importances, SHAP, an LLM or causal assertions.

Use decimal arithmetic (28-digit precision) and round-half-even to two decimal places only for final scores; no component is rounded before summing. Audit components retain up to 12 decimal places. Explanation contributions display two decimals; rounded displayed components can differ slightly from the rounded total. Original source fields are unchanged strings, including zero-padded HHMM. Summary grid bounds use two decimal degrees, mean FRP two decimals in MW, and summary/distribution scores two decimals. Grid indices are calculated before formatting, with Decimal floor division by exactly 0.05 to avoid binary-float edge errors. CSVs use UTF-8, LF, fixed field order and empty cells for nulls.

## Local review queues and daily summaries

hotspot_risk_audit.csv has all 674 rows in the original order and exactly the requested 14 audit fields. classified_hotspots.csv retains exactly its 16 contract fields; only risk_score/risk_band change and every class_probability stays null. high_priority_alerts.csv contains only high/critical rows and the requested 17 fields. alert_id is `ALT-` + unchanged hotspot_id. Sort by descending score, persistence, FRP, then ascending date, time, ID. This is an alert-ready local review queue; no delivery system is implemented or invoked.

daily_alert_summary.csv groups only those selected rows by acquisition date and fixed globally anchored 0.05-degree latitude/longitude cells. Indices are floor(latitude/0.05) and floor(longitude/0.05). South/west edges are included, north/east edges excluded. Group ID is `YYYYMMDD-lat_index-lon_index`. Different dates never merge. Summary rows sort by date then latitude index then longitude index. Representative selection uses exactly the hotspot alert ranking. Highest band uses critical > high > moderate > low. Counts, maximum score, class counts, mean FRP, maximum persistence and representative ID come only from group members. A grid cell is not a fire perimeter, an incident boundary or a deduplicated event.

risk_score_distribution.csv contains all 20 combinations of industrial/wildfire/unknown/overall and critical/high/moderate/low/all in that category order. Zero-count combinations have null statistics. The all rows are class subtotals; overall/band are cross-class subtotals; overall/all is the grand total 674. Do not sum these redundant subtotal rows together. Median and mean operate on the stored two-decimal final scores, then round to two decimals.

## Reproducibility, preservation and presentation

Every artifact is computed and validated before publishing. Each output is written to a same-directory temporary file, flushed, fsynced and atomically replaced. The CSV group is not a transaction: an interruption during publishing requires a rerun and hash verification. Only the classified CSV and README.md are permitted earlier-file modifications. No dependency is added: the scoring script uses Python's standard library. Source/model/cache/report/test hashes are checked before and after execution; no pre-existing file except the two permitted paths changes. README changes solely add Stage 5 execution, interpretation and validation instructions.

Both first and cached runs block network connections and model imports, and must reproduce all five required CSV hashes. Validation includes the accepted Stage 4 hash, actual inputs, counts and final output hashes. Operational log cache status is not serialized into artifacts. No changing timestamp enters deterministic outputs. The preserved full test suite still exercises isolated Stage 4 classifier fixtures; Stage 5 itself never loads the saved models or fits any model.

Present `Review priority: high (score 62.00/100)` and `Rule-based context category: industrial`, with component points and this document's opening disclaimer. Do not present these as emergency levels, true fire causes, calibrated probabilities, predicted damage or verified severity. Unknown context can still have high review priority; low priority does not establish safety. Repeated detections are not separate verified incidents, persistent thermal sources may be routine activity, coarse sensor locations are not fire outlines, and clouds/overpass timing/geolocation jitter affect observations. The score has no independently verified severity validation. No frontend, external alert transmission or Stage 6 work is included.
