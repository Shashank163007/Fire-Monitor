"""Frozen typed snapshot and response contracts; no classifier model objects."""
from datetime import date
from typing import Annotated, Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator

CandidateClass = Literal["industrial", "wildfire", "unknown"]
RiskBand = Literal["critical", "high", "moderate", "low"]
DayNight = Literal["D", "N"]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegative = Annotated[float, Field(ge=0)]
Score = Annotated[float, Field(ge=0, le=100)]
DateText = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ClassCounts(Frozen):
    industrial: int = Field(ge=0)
    wildfire: int = Field(ge=0)
    unknown: int = Field(ge=0)


class RiskCounts(Frozen):
    critical: int = Field(ge=0)
    high: int = Field(ge=0)
    moderate: int = Field(ge=0)
    low: int = Field(ge=0)


class Bounds(Frozen):
    min_latitude: Literal[21.0]
    max_latitude: Literal[24.0]
    min_longitude: Literal[72.0]
    max_longitude: Literal[75.0]
    boundary_policy: Literal["south_west_inclusive_north_east_exclusive"]


class Period(Frozen):
    date_from: Literal["2026-06-01"]
    date_to: Literal["2026-06-30"]


class Hotspot(Frozen):
    hotspot_id: Hash
    latitude: float = Field(ge=21, lt=24)
    longitude: float = Field(ge=72, lt=75)
    acq_date: DateText
    acq_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3])[0-5][0-9]$")
    frp: NonNegative
    brightness: float = Field(gt=0)
    confidence: Literal["l", "n", "h"]
    day_night: DayNight
    distance_to_industrial_km: NonNegative | None
    persistence_count_30d: int = Field(ge=1, le=30, strict=True)
    land_cover_class: str = Field(min_length=1)
    predicted_class: CandidateClass
    classification_source: Literal["rule_based_weak_label_fallback"]
    class_probability: None
    risk_score: Score
    risk_band: RiskBand
    frp_points: float = Field(ge=0, le=40)
    persistence_points: float = Field(ge=0, le=30)
    confidence_points: float = Field(ge=0, le=20)
    night_points: float = Field(ge=0, le=10)
    primary_risk_driver: Literal["thermal_intensity", "persistence", "observation_confidence", "night_observation"]
    explanation: str = Field(min_length=1)

    @field_validator("acq_date")
    @classmethod
    def locked_date(cls, value: str) -> str:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or not "2026-06-01" <= value <= "2026-06-30":
            raise ValueError("Date outside locked June 2026 scope")
        return value


class Alert(Hotspot):
    alert_id: str


class AlertGroup(Frozen):
    alert_group_id: str
    acq_date: DateText
    grid_min_latitude: float
    grid_max_latitude: float
    grid_min_longitude: float
    grid_max_longitude: float
    hotspot_count: int = Field(gt=0, strict=True)
    maximum_risk_score: Score
    highest_risk_band: Literal["high", "critical"]
    industrial_count: int = Field(ge=0, strict=True)
    wildfire_count: int = Field(ge=0, strict=True)
    unknown_count: int = Field(ge=0, strict=True)
    mean_frp: NonNegative
    maximum_persistence_count_30d: int = Field(ge=1, le=30, strict=True)
    representative_hotspot_id: Hash
    group_explanation: str


class DistributionRow(Frozen):
    predicted_class: Literal["industrial", "wildfire", "unknown", "overall"]
    risk_band: Literal["critical", "high", "moderate", "low", "all"]
    hotspot_count: int = Field(ge=0, strict=True)
    minimum_score: Score | None
    median_score: Score | None
    mean_score: Score | None
    maximum_score: Score | None


class FileHash(Frozen):
    filename: str
    sha256: Hash


class Manifest(Frozen):
    schema_version: Literal["1.0.0"]
    generated_from_stage: Literal[5]
    generated_at_policy: Literal["omitted_for_deterministic_export"]
    dataset_mode: Literal["retrospective_demo"]
    region_bounds: Bounds
    period: Period
    total_hotspots: Literal[674]
    class_counts: ClassCounts
    risk_band_counts: RiskCounts
    high_priority_alert_count: Literal[10]
    daily_alert_group_count: Literal[6]
    classification_source: Literal["rule_based_weak_label_fallback"]
    classifier_operational: Literal[False]
    source_file_hashes: tuple[FileHash, ...]
    exported_file_hashes: tuple[FileHash, ...]
    risk_distribution: tuple[DistributionRow, ...]
    limitations: tuple[str, ...]
    disclaimer: str


class Health(Frozen):
    status: Literal["ok"] = "ok"
    service: str
    schema_version: str
    dataset_loaded: Literal[True] = True
    total_hotspots: int


class Metadata(Frozen):
    project_title: str
    dataset_mode: str
    geographic_bounds: Bounds
    period: Period
    classification_source: str
    classifier_operational: bool
    scoring_method: str
    total_hotspots: int
    class_counts: ClassCounts
    risk_band_counts: RiskCounts
    source_stage: int
    data_disclaimer: str
    limitations: tuple[str, ...]


class NumericSummary(Frozen):
    minimum: float
    median: float
    mean: float
    maximum: float


class Statistics(Frozen):
    total_hotspots: int
    class_counts: ClassCounts
    risk_band_counts: RiskCounts
    day_night_counts: dict[str, int]
    confidence_counts: dict[str, int]
    high_priority_alert_count: int
    alert_group_count: int
    risk_score: NumericSummary
    frp: NumericSummary
    persistence: NumericSummary


T = TypeVar("T")


class Page(Frozen, Generic[T]):
    items: tuple[T, ...]
    total: int
    limit: int
    offset: int
    returned: int
    applied_filters: dict[str, str | int | float]
    sort_by: str
    sort_order: str


class Point(Frozen):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class GeoProperties(Frozen):
    hotspot_id: str
    acq_date: str
    acq_time: str
    predicted_class: CandidateClass
    classification_source: str
    frp: float
    persistence_count_30d: int
    risk_score: float
    risk_band: RiskBand
    day_night: DayNight
    confidence: str
    primary_risk_driver: str
    explanation: str


class Feature(Frozen):
    type: Literal["Feature"] = "Feature"
    geometry: Point
    properties: GeoProperties


class FeatureCollection(Frozen):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[Feature, ...]


class RiskDistribution(Frozen):
    items: tuple[DistributionRow, ...]
    total_hotspots: int
