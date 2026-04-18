from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TransportMode = Literal["rail", "drive"]
PaceMode = Literal["slow", "balanced", "dense"]
JobStatus = Literal["ready", "collecting", "partial_result", "awaiting_login", "failed", "completed"]
CandidateKind = Literal["hotel", "strategy", "region_hint"]
PriceConfidence = Literal["observed", "hidden", "estimated"]
ShareVisibility = Literal["token"]


class Travelers(BaseModel):
    adults: int = Field(ge=1, le=12)
    children: int = Field(default=0, ge=0, le=8)


class TripRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=40)
    destination: str = Field(min_length=1, max_length=40)
    start_date: date
    end_date: date | None = None
    days: int | None = Field(default=None, ge=1, le=15)
    travelers: Travelers
    transport_mode: TransportMode
    hotel_budget_min: float | None = Field(default=None, ge=0)
    hotel_budget_max: float | None = Field(default=None, ge=0)
    hotel_star_level: int | None = Field(default=None, ge=1, le=5)
    pace: PaceMode = "balanced"
    must_go: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    hotel_preferences: list[str] = Field(default_factory=list)
    parking_required: bool = False

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("must_go", "avoid", "hotel_preferences", mode="before")
    @classmethod
    def normalize_list(cls, value: str | list[str] | None) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]

    @model_validator(mode="after")
    def derive_trip_length(self) -> "TripRequest":
        if self.end_date is None and self.days is None:
            raise ValueError("Either end_date or days is required.")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date.")
        if self.end_date is None and self.days is not None:
            self.end_date = self.start_date + timedelta(days=self.days - 1)
        if self.end_date is not None:
            self.days = (self.end_date - self.start_date).days + 1
        if self.hotel_budget_min and self.hotel_budget_max and self.hotel_budget_min > self.hotel_budget_max:
            raise ValueError("hotel_budget_min cannot be greater than hotel_budget_max.")
        return self

    @property
    def nights(self) -> int:
        return max((self.days or 1) - 1, 1)


class SourceStatus(BaseModel):
    source: str
    state: Literal["ready", "awaiting_login", "failed", "unknown"]
    detail: str
    checked_at: datetime


class SourceEvidence(BaseModel):
    source: str
    title: str
    url: str
    captured_at: datetime
    excerpt: str = ""


class GuideNote(BaseModel):
    source: str = "xiaohongshu"
    title: str
    url: str
    excerpt: str
    pois: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


class PoiCandidate(BaseModel):
    name: str
    district: str = ""
    category: str = "attraction"
    reason: str = ""
    estimated_visit_minutes: int = 90


class TransportOption(BaseModel):
    source: str
    mode: TransportMode
    label: str
    depart_at: str = ""
    arrive_at: str = ""
    duration_minutes: int = 0
    price_snapshot: float | None = None
    tags: list[str] = Field(default_factory=list)
    booking_url: str = ""


class HotelCandidate(BaseModel):
    source: str
    name: str
    district: str = ""
    nightly_price: float
    candidate_kind: CandidateKind = "hotel"
    price_confidence: PriceConfidence = "observed"
    rating: float | None = None
    tags: list[str] = Field(default_factory=list)
    breakfast_included: bool = False
    free_cancel: bool = False
    parking: bool = False
    booking_url: str = ""
    score: float | None = None
    why_selected: str = ""


class BudgetEstimate(BaseModel):
    currency: str = "CNY"
    rail_or_drive_total: float = 0
    hotel_total: float = 0
    daily_food_and_misc_total: float = 0

    @property
    def grand_total(self) -> float:
        return round(self.rail_or_drive_total + self.hotel_total + self.daily_food_and_misc_total, 2)


class DailyPlan(BaseModel):
    day_index: int
    date: date
    theme: str
    morning: str
    afternoon: str
    evening: str
    lodging: str = ""


class TripPlanResult(BaseModel):
    summary: str
    daily_itinerary: list[DailyPlan]
    transport_options: list[TransportOption]
    hotel_candidates: list[HotelCandidate]
    budget_estimate: BudgetEstimate
    source_evidence: list[SourceEvidence]
    warnings: list[str] = Field(default_factory=list)
    guide_notes: list[GuideNote] = Field(default_factory=list)
    pois: list[PoiCandidate] = Field(default_factory=list)


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    request: TripRequest
    created_at: datetime
    updated_at: datetime
    progress: int = 0
    result: TripPlanResult | None = None
    warnings: list[str] = Field(default_factory=list)
    source_statuses: dict[str, SourceStatus] = Field(default_factory=dict)
    error: str | None = None
    checkpoint: dict = Field(default_factory=dict, exclude=True)


class TripShareSnapshot(BaseModel):
    snapshot_id: str
    job_id: str
    title: str
    payload: dict[str, Any]
    created_at: datetime


class TripShareLink(BaseModel):
    token: str
    snapshot_id: str
    visibility: ShareVisibility = "token"
    expires_at: datetime | None = None
    created_at: datetime
    last_accessed_at: datetime | None = None
    revoked_at: datetime | None = None


class TripShareCreateRequest(BaseModel):
    visibility: ShareVisibility = "token"


class TripShareCreateResponse(BaseModel):
    token: str
    snapshot_id: str
    share_url: str
    excel_url: str
    pdf_url: str
    public_base_url: str | None = None
    public_share_url: str | None = None
    public_excel_url: str | None = None
    public_pdf_url: str | None = None
    local_share_url: str | None = None
    local_excel_url: str | None = None
    local_pdf_url: str | None = None
