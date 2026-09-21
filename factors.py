"""Loads the emission factor and grid intensity data models from JSON.

Two kinds of activity factor exist:

* ``fixed``: a flat kg CO2e per unit (for example petrol car, per km).
* ``electricity``: kWh used per unit, multiplied by the grid intensity of the
  user's region. This is what makes the estimate localised.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FALLBACK_REGION = "GLOBAL"


class UnknownActivityError(ValueError):
    """Raised when an activity type is not in the factor table."""


@dataclass(frozen=True)
class ActivityFactor:
    key: str
    category: str
    label: str
    unit: str
    kind: str  # "fixed" or "electricity"
    kg_co2e_per_unit: float | None
    kwh_per_unit: float | None
    confidence: str
    source: str
    note: str


@dataclass(frozen=True)
class GridRegion:
    code: str
    name: str
    kg_co2e_per_kwh: float
    year: str
    source: str


def normalise_region(region: str | None) -> str:
    return (region or FALLBACK_REGION).strip().upper()


class FactorStore:
    def __init__(self, factors_path: Path | None = None, grid_path: Path | None = None):
        factors_path = factors_path or DATA_DIR / "emission_factors.json"
        grid_path = grid_path or DATA_DIR / "grid_intensity.json"
        self._activities = self._load_activities(factors_path)
        self._regions = self._load_regions(grid_path)

    @staticmethod
    def _load_activities(path: Path) -> dict[str, ActivityFactor]:
        raw = json.loads(path.read_text(encoding="utf-8"))["factors"]
        activities = {}
        for key, item in raw.items():
            kind = item["kind"]
            if kind == "fixed" and item.get("kg_co2e_per_unit") is None:
                raise ValueError(f"{key}: fixed factors need kg_co2e_per_unit")
            if kind == "electricity" and item.get("kwh_per_unit") is None:
                raise ValueError(f"{key}: electricity factors need kwh_per_unit")
            if kind not in ("fixed", "electricity"):
                raise ValueError(f"{key}: unknown kind '{kind}'")
            activities[key] = ActivityFactor(
                key=key,
                category=item["category"],
                label=item["label"],
                unit=item["unit"],
                kind=kind,
                kg_co2e_per_unit=item.get("kg_co2e_per_unit"),
                kwh_per_unit=item.get("kwh_per_unit"),
                confidence=item["confidence"],
                source=item["source"],
                note=item.get("note", ""),
            )
        return activities

    @staticmethod
    def _load_regions(path: Path) -> dict[str, GridRegion]:
        raw = json.loads(path.read_text(encoding="utf-8"))["regions"]
        if FALLBACK_REGION not in raw:
            raise ValueError(f"grid data must include a {FALLBACK_REGION} entry")
        return {
            code.upper(): GridRegion(
                code=code.upper(),
                name=item["name"],
                kg_co2e_per_kwh=item["kg_co2e_per_kwh"],
                year=item["year"],
                source=item["source"],
            )
            for code, item in raw.items()
        }

    def activity(self, key: str) -> ActivityFactor:
        try:
            return self._activities[key]
        except KeyError:
            raise UnknownActivityError(
                f"Unknown activity_type '{key}'. See GET /factors for the supported types."
            ) from None

    def activities(self) -> list[ActivityFactor]:
        return list(self._activities.values())

    def regions(self) -> list[GridRegion]:
        return list(self._regions.values())

    def grid(self, region: str | None) -> tuple[GridRegion, bool]:
        """Find the grid intensity for a region.

        Tries the exact code (IN-UP), then the country part (IN), then the
        world average. The second value says whether a fallback was used.
        """
        code = normalise_region(region)
        if code in self._regions:
            return self._regions[code], False
        country = code.split("-")[0]
        if country in self._regions:
            return self._regions[country], False
        return self._regions[FALLBACK_REGION], True
