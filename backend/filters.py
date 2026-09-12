"""Strict query contracts and pure filtering over immutable snapshot records."""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .data_loader import default_key
from .models import CandidateClass, DayNight, Hotspot, RiskBand


class ScientificFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    predicted_class: CandidateClass | None = None
    risk_band: RiskBand | None = None
    date_from: str | None = None
    date_to: str | None = None
    day_night: DayNight | None = None
    min_frp: float | None = Field(default=None, ge=0)
    max_frp: float | None = Field(default=None, ge=0)
    min_risk_score: float | None = Field(default=None, ge=0, le=100)
    max_risk_score: float | None = Field(default=None, ge=0, le=100)
    min_persistence: int | None = Field(default=None, ge=1, le=30)
    bbox: str | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def iso_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use exact YYYY-MM-DD dates")
        return value

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, value):
        if value is not None:
            bbox_values(value)
        return value

    @model_validator(mode="after")
    def ordered_ranges(self):
        for low, high in [(self.date_from, self.date_to), (self.min_frp, self.max_frp), (self.min_risk_score, self.max_risk_score)]:
            if low is not None and high is not None and low > high:
                raise ValueError("Range minimum must not exceed maximum")
        return self


SortField = Literal["acq_date", "acq_time", "frp", "persistence_count_30d", "risk_score", "predicted_class", "risk_band", "hotspot_id"]


class HotspotQuery(ScientificFilters):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: SortField = "acq_date"
    sort_order: Literal["asc", "desc"] = "asc"


class GroupQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: str | None = None
    date_to: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    _dates = field_validator("date_from", "date_to")(ScientificFilters.iso_date.__func__)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not exceed date_to")
        return self


class AlertQuery(GroupQuery):
    predicted_class: CandidateClass | None = None


def bbox_values(text: str) -> tuple[float, float, float, float]:
    try:
        parts = tuple(Decimal(p.strip()) for p in text.split(","))
    except InvalidOperation:
        raise ValueError("bbox must have four finite longitude/latitude numbers") from None
    if len(parts) != 4 or not all(p.is_finite() for p in parts):
        raise ValueError("bbox must have four finite longitude/latitude numbers")
    west, south, east, north = parts
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox bounds must be ordered and within WGS84 ranges")
    return tuple(float(p) for p in parts)


def filter_hotspots(rows: tuple[Hotspot, ...], query: ScientificFilters) -> list[Hotspot]:
    bounds = bbox_values(query.bbox) if query.bbox else None
    result = []
    for h in rows:
        if any(getattr(query, k) is not None and getattr(h, k) != getattr(query, k) for k in ["predicted_class", "risk_band", "day_night"]):
            continue
        if query.date_from and h.acq_date < query.date_from or query.date_to and h.acq_date > query.date_to:
            continue
        if any(value is not None and measured < value for value, measured in [(query.min_frp,h.frp),(query.min_risk_score,h.risk_score),(query.min_persistence,h.persistence_count_30d)]):
            continue
        if any(value is not None and measured > value for value, measured in [(query.max_frp,h.frp),(query.max_risk_score,h.risk_score)]):
            continue
        if bounds and not (bounds[0] <= h.longitude <= bounds[2] and bounds[1] <= h.latitude <= bounds[3]):
            continue
        result.append(h)
    return result


def sort_hotspots(rows, field="acq_date", order="asc") -> list[Hotspot]:
    # Stable second sort retains the ascending date/time/ID tie-break even for desc.
    ordered = sorted(rows, key=default_key)
    severity = {"low":0, "moderate":1, "high":2, "critical":3}
    return sorted(ordered, key=lambda h: severity[h.risk_band] if field == "risk_band" else getattr(h,field), reverse=order=="desc")


def applied(query) -> dict:
    return query.model_dump(exclude_none=True, exclude={"limit", "offset", "sort_by", "sort_order"})
