# Locked data interface

The future `classified_hotspots.csv` interface has exactly these fields, in this order:

```text
hotspot_id
latitude
longitude
acq_date
acq_time
frp
brightness
confidence
day_night
distance_to_industrial_km
persistence_count_30d
land_cover_class
predicted_class
class_probability
risk_score
risk_band
```

No additional output fields may be added without an explicit contract revision.

| Field | Representation and meaning |
| --- | --- |
| hotspot_id | Stable string identifying a satellite/instrument/location/UTC acquisition observation. |
| latitude | Float, WGS84 degrees, [-90, 90]. |
| longitude | Float, WGS84 degrees, [-180, 180]. |
| acq_date | UTC date string, YYYY-MM-DD. |
| acq_time | UTC time string, four digits HHMM; preserve leading zeroes. |
| frp | Nonnegative float, FIRMS fire radiative power in MW; nullable when unavailable. |
| brightness | Positive float in kelvin, retained from the supplied VIIRS brightness column; nullable when unavailable. |
| confidence | VIIRS categorical string: l, n, h; nullable when unavailable. Not a probability. |
| day_night | D or N; nullable when unavailable. |
| distance_to_industrial_km | Nonnegative float in km; null until spatial enrichment is available. |
| persistence_count_30d | Nonnegative integer; null until computed using the locked 30-day window. Grid size, inclusion of current day, and observation coverage must be documented before computation. |
| land_cover_class | String; null until enrichment. Record source legend when implemented. |
| predicted_class | industrial, flare, wildfire, or agburn; null until classification. |
| class_probability | Float in [0, 1] for the predicted class; null until a model provides it. Not verified fire-cause certainty. |
| risk_score | Heuristic score; null until implemented. Scale and weights must be documented before publishing values. Never an ML escalation prediction. |
| risk_band | String; null until heuristic thresholds and scale are documented. |

CSV nulls are empty cells; JSON nulls are `null`. Future labels are weak/proxy labels, not verified ground truth. No ground-truth accuracy claim is supported.

`feature_importances.json` has exactly this documented shape:

```json
[
  {"feature": "feature_name", "importance": 0.0}
]
```

The example specifies a schema only. Actual values must come from the trained Random Forest's `feature_importances_`, with feature names in model-input order. This stage creates neither that JSON file nor classified outputs.

Stage-one `data/processed/firms_normalized.csv` is an intermediate ingestion dataset, not this final interface. It retains source metadata, including nullable archive `type`, for traceability; it contains no fabricated enrichment, predictions, probabilities, or risk values. Archive `type` is source metadata, never a verified target label.
