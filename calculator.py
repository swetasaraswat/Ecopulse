"""Turns a logged activity into an estimate of kg CO2e."""

from dataclasses import dataclass

from .factors import FactorStore


@dataclass(frozen=True)
class EmissionEstimate:
    activity_type: str
    category: str
    label: str
    quantity: float
    unit: str
    factor_kg_co2e_per_unit: float
    co2e_kg: float
    region_used: str | None  # only set for activities that depend on the grid
    grid_fallback: bool
    confidence: str


class EmissionCalculator:
    def __init__(self, store: FactorStore):
        self.store = store

    def factor_per_unit(self, activity_type: str, region: str | None) -> tuple[float, str | None, bool]:
        """Return (kg CO2e per unit, grid region used, whether a fallback grid was used)."""
        factor = self.store.activity(activity_type)
        if factor.kind == "fixed":
            return factor.kg_co2e_per_unit, None, False
        grid, fallback = self.store.grid(region)
        return factor.kwh_per_unit * grid.kg_co2e_per_kwh, grid.code, fallback

    def estimate(self, activity_type: str, quantity: float, region: str | None) -> EmissionEstimate:
        if quantity < 0:
            raise ValueError("quantity cannot be negative")
        factor = self.store.activity(activity_type)
        per_unit, region_used, fallback = self.factor_per_unit(activity_type, region)
        return EmissionEstimate(
            activity_type=factor.key,
            category=factor.category,
            label=factor.label,
            quantity=quantity,
            unit=factor.unit,
            factor_kg_co2e_per_unit=round(per_unit, 4),
            co2e_kg=round(per_unit * quantity, 4),
            region_used=region_used,
            grid_fallback=fallback,
            confidence=factor.confidence,
        )
