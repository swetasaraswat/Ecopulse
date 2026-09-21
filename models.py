"""Request and response schemas for the REST API."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

REGION_PATTERN = r"^[A-Za-z]{2,6}(-[A-Za-z0-9]{1,6})?$"


class ActivityIn(BaseModel):
    activity_type: str = Field(..., examples=["car_petrol"], description="One of the keys from GET /factors.")
    quantity: float = Field(..., gt=0, le=100000, description="Amount in the unit of the activity (km, kWh, meal or kg).")
    notes: str | None = Field(None, max_length=200)


class Estimate(BaseModel):
    activity_type: str
    category: str
    label: str
    quantity: float
    unit: str
    factor_kg_co2e_per_unit: float
    co2e_kg: float
    region_used: str | None = Field(None, description="Grid region used. Only set for electricity-based activities.")
    grid_fallback: bool = Field(False, description="True if the requested region was unknown and the world average was used.")
    confidence: str


class EstimateRequest(BaseModel):
    region: str = Field("IN", pattern=REGION_PATTERN, examples=["IN"])
    activities: list[ActivityIn] = Field(..., min_length=1, max_length=100)


class EstimateResponse(BaseModel):
    region: str
    total_co2e_kg: float
    items: list[Estimate]


class UserIn(BaseModel):
    region: str = Field("IN", pattern=REGION_PATTERN, examples=["IN"], description="Country or region code used to pick the grid intensity.")


class UserOut(BaseModel):
    user_id: str
    region: str
    created_at: str


class LogActivitiesRequest(BaseModel):
    date: dt.date | None = Field(None, description="Day the activities happened. Defaults to today.")
    activities: list[ActivityIn] = Field(..., min_length=1, max_length=100)


class LoggedActivity(Estimate):
    id: int
    date: dt.date
    notes: str | None = None


class LogActivitiesResponse(BaseModel):
    user_id: str
    date: dt.date
    total_co2e_kg: float
    logged: list[LoggedActivity]


class FootprintResponse(BaseModel):
    user_id: str
    date: dt.date
    total_co2e_kg: float
    by_category: dict[str, float]
    activities: list[LoggedActivity]


class HistoryDay(BaseModel):
    date: dt.date
    co2e_kg: float


class HistoryResponse(BaseModel):
    user_id: str
    start: dt.date
    end: dt.date
    total_co2e_kg: float
    average_daily_co2e_kg: float
    by_category: dict[str, float]
    days: list[HistoryDay]


class Suggestion(BaseModel):
    candidate_id: str | None = Field(None, description="Which habit-change rule this came from.")
    title: str
    message: str
    category: str
    weekly_saving_kg_co2e: float | None = Field(
        None, description="Estimated saving per week if the habit change is adopted. Calculated from the factor model."
    )


class RecommendationResponse(BaseModel):
    user_id: str
    window_start: dt.date
    window_end: dt.date
    source: Literal["gemini", "rules"] = Field(description="Which engine wrote the wording.")
    fallback_reason: str | None = Field(None, description="Why the rule-based engine was used instead of the AI one, if it was.")
    summary: str
    suggestions: list[Suggestion]


class FactorOut(BaseModel):
    key: str
    label: str
    category: str
    unit: str
    kind: Literal["fixed", "electricity"]
    kg_co2e_per_unit: float | None = None
    kwh_per_unit: float | None = None
    confidence: str
    source: str
    note: str


class RegionOut(BaseModel):
    code: str
    name: str
    kg_co2e_per_kwh: float
    year: str
    source: str


class HealthResponse(BaseModel):
    status: str
    version: str
    ai_enabled: bool
