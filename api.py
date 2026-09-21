"""REST endpoints."""

import datetime as dt
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from . import __version__
from .emissions import UnknownActivityError
from .emissions.factors import normalise_region
from .models import (
    EstimateRequest,
    EstimateResponse,
    FactorOut,
    FootprintResponse,
    HealthResponse,
    HistoryDay,
    HistoryResponse,
    LoggedActivity,
    LogActivitiesRequest,
    LogActivitiesResponse,
    RecommendationResponse,
    RegionOut,
    Estimate,
    UserIn,
    UserOut,
)
from .services import Services

router = APIRouter()

UserId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.-]{1,64}$", description="Letters, numbers, dot, dash or underscore.")]


def get_services(request: Request) -> Services:
    return request.app.state.services


Svc = Annotated[Services, Depends(get_services)]


def _require_user(svc: Services, user_id: str) -> dict:
    user = svc.storage.get_user(user_id)
    if user is None:
        raise HTTPException(404, f"Unknown user '{user_id}'. Create one first with PUT /users/{user_id}.")
    return user


def _logged(row: dict) -> LoggedActivity:
    return LoggedActivity(
        id=row["id"],
        date=row["activity_date"],
        notes=row["notes"],
        activity_type=row["activity_type"],
        category=row["category"],
        label=row["label"],
        quantity=row["quantity"],
        unit=row["unit"],
        factor_kg_co2e_per_unit=row["factor"],
        co2e_kg=row["co2e_kg"],
        region_used=row["region_used"],
        grid_fallback=bool(row["grid_fallback"]),
        confidence=row["confidence"],
    )


# --- reference data ----------------------------------------------------------
@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(svc: Svc):
    return HealthResponse(status="ok", version=__version__, ai_enabled=svc.ai_enabled)


@router.get("/factors", response_model=list[FactorOut], tags=["reference data"])
def list_factors(svc: Svc):
    """Every activity type EcoPulse can estimate, with its emission factor and where it came from."""
    return [FactorOut(**asdict(f)) for f in svc.factors.activities()]


@router.get("/regions", response_model=list[RegionOut], tags=["reference data"])
def list_regions(svc: Svc):
    """Grid carbon intensity by region. This is what localises electricity-based estimates."""
    return [RegionOut(**asdict(r)) for r in svc.factors.regions()]


# --- stateless estimate ------------------------------------------------------
@router.post("/estimate", response_model=EstimateResponse, tags=["estimates"])
def estimate(body: EstimateRequest, svc: Svc):
    """Estimate emissions for a list of activities without saving anything."""
    region = normalise_region(body.region)
    try:
        items = [svc.calculator.estimate(a.activity_type, a.quantity, region) for a in body.activities]
    except UnknownActivityError as err:
        raise HTTPException(422, str(err)) from err
    return EstimateResponse(
        region=region,
        total_co2e_kg=round(sum(i.co2e_kg for i in items), 3),
        items=[Estimate(**asdict(i)) for i in items],
    )


# --- users and activities ----------------------------------------------------
@router.put("/users/{user_id}", response_model=UserOut, tags=["users"])
def put_user(user_id: UserId, body: UserIn, svc: Svc):
    """Create a user or change their region."""
    return UserOut(**svc.storage.upsert_user(user_id, normalise_region(body.region)))


@router.get("/users/{user_id}", response_model=UserOut, tags=["users"])
def get_user(user_id: UserId, svc: Svc):
    return UserOut(**_require_user(svc, user_id))


@router.post("/users/{user_id}/activities", response_model=LogActivitiesResponse, status_code=201, tags=["activities"])
def log_activities(user_id: UserId, body: LogActivitiesRequest, svc: Svc):
    """Log one or more activities for a day. Emissions are estimated using the user's region."""
    user = _require_user(svc, user_id)
    day = body.date or dt.date.today()
    try:
        estimates = [(svc.calculator.estimate(a.activity_type, a.quantity, user["region"]), a.notes) for a in body.activities]
    except UnknownActivityError as err:
        raise HTTPException(422, str(err)) from err
    ids = svc.storage.add_activities(user_id, day, estimates)
    logged = [
        LoggedActivity(id=i, date=day, notes=notes, **asdict(est))
        for i, (est, notes) in zip(ids, estimates)
    ]
    return LogActivitiesResponse(
        user_id=user_id,
        date=day,
        total_co2e_kg=round(sum(e.co2e_kg for e, _ in estimates), 3),
        logged=logged,
    )


@router.get("/users/{user_id}/footprint", response_model=FootprintResponse, tags=["activities"])
def daily_footprint(
    user_id: UserId,
    svc: Svc,
    date: Annotated[dt.date | None, Query(description="Defaults to today.")] = None,
):
    """Total emissions for one day, split by category."""
    _require_user(svc, user_id)
    day = date or dt.date.today()
    rows = svc.storage.activities_on(user_id, day)
    by_category: dict[str, float] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0.0) + row["co2e_kg"]
    return FootprintResponse(
        user_id=user_id,
        date=day,
        total_co2e_kg=round(sum(by_category.values()), 3),
        by_category={k: round(v, 3) for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])},
        activities=[_logged(r) for r in rows],
    )


@router.get("/users/{user_id}/history", response_model=HistoryResponse, tags=["activities"])
def history(
    user_id: UserId,
    svc: Svc,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    end: Annotated[dt.date | None, Query(description="Last day of the window. Defaults to today.")] = None,
):
    """Daily totals for the last N days, with zeros filled in for days with nothing logged."""
    _require_user(svc, user_id)
    end_day = end or dt.date.today()
    start_day = end_day - dt.timedelta(days=days - 1)
    totals = svc.storage.daily_totals(user_id, start_day, end_day)
    day_list = [start_day + dt.timedelta(days=i) for i in range(days)]
    total = sum(totals.values())
    return HistoryResponse(
        user_id=user_id,
        start=start_day,
        end=end_day,
        total_co2e_kg=round(total, 3),
        average_daily_co2e_kg=round(total / days, 3),
        by_category={k: round(v, 3) for k, v in svc.storage.category_totals(user_id, start_day, end_day).items()},
        days=[HistoryDay(date=d, co2e_kg=round(totals.get(d.isoformat(), 0.0), 3)) for d in day_list],
    )


# --- recommendations ---------------------------------------------------------
@router.get("/users/{user_id}/recommendations", response_model=RecommendationResponse, tags=["recommendations"])
def recommendations(
    user_id: UserId,
    svc: Svc,
    days: Annotated[int, Query(ge=1, le=30, description="How many recent days of history to use.")] = 7,
    end: Annotated[dt.date | None, Query(description="Last day of the window. Defaults to today.")] = None,
    ai: Annotated[bool, Query(description="Set to false to skip the AI step and use rule-based wording.")] = True,
):
    """Personalised habit suggestions based on the user's recent activity."""
    user = _require_user(svc, user_id)
    result = svc.engine.recommend(user, end or dt.date.today(), days=days, use_ai=ai)
    return RecommendationResponse(user_id=user_id, **asdict(result))
