"""Rule-based habit candidates.

Each rule in data/swaps.json proposes a change (swap to a lower-carbon
alternative, or cut back) for something the user actually logged. The saving is
worked out here from the emission factor model, so the numbers are never
written by a language model.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ..emissions import EmissionCalculator

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "swaps.json"
MIN_WEEKLY_SAVING_KG = 0.05


@dataclass(frozen=True)
class Candidate:
    id: str
    title: str
    action: str
    category: str
    weekly_saving_kg_co2e: float
    evidence: str


def load_rules(path: Path = DATA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    if value >= 10:
        return str(int(round(value)))
    return f"{value:.1f}"


def build_candidates(
    type_totals: list[dict],
    days: int,
    region: str,
    calculator: EmissionCalculator,
    rules: dict | None = None,
) -> list[Candidate]:
    """Match rules against what the user logged and rank them by weekly saving."""
    rules = rules or load_rules()
    logged = {row["activity_type"]: row for row in type_totals}
    weekly_scale = 7 / days
    candidates = []

    for rule in rules["rules"]:
        row = logged.get(rule["from"])
        if row is None:
            continue
        weekly_qty = row["quantity"] * weekly_scale
        shifted = weekly_qty * rule["share"]
        from_factor, _, _ = calculator.factor_per_unit(rule["from"], region)
        to_factor = 0.0
        if rule["to"]:
            to_factor, _, _ = calculator.factor_per_unit(rule["to"], region)
        saving = shifted * (from_factor - to_factor)
        if saving < MIN_WEEKLY_SAVING_KG:
            continue
        candidates.append(
            Candidate(
                id=rule["id"],
                title=rule["title"],
                action=rule["action"].format(shifted=_fmt(shifted)),
                category=rule["category"],
                weekly_saving_kg_co2e=round(saving, 2),
                evidence=f"{_fmt(row['quantity'])} {row['unit']} of {row['label'].lower()} in the last {days} days",
            )
        )

    return sorted(candidates, key=lambda c: c.weekly_saving_kg_co2e, reverse=True)


def starter_tips(rules: dict | None = None) -> list[dict]:
    return (rules or load_rules())["starter_tips"]
