"""Habit recommendation engine.

It works in two steps:

1. Rules (rules.py) look at what the user logged and calculate candidate habit
   changes with real savings from the emission factor model.
2. If a Gemini client is configured, the model picks the best candidates for
   this person and writes friendly wording. Its reply is validated, and the
   saving numbers always come from step 1. If anything goes wrong, the
   rule-based wording is used instead, so the endpoint never fails because the
   AI did.
"""

import datetime as dt
import json
from dataclasses import dataclass, field

from ..emissions import EmissionCalculator
from ..storage import Storage
from . import rules as rules_module
from .gemini_client import GeminiClient, GeminiError
from .prompts import SYSTEM_INSTRUCTION, build_user_payload

CATEGORY_NAMES = {"transport": "travel", "energy": "home energy", "food": "food", "waste": "waste"}
MAX_CANDIDATES_TO_MODEL = 8


@dataclass
class RecommendationResult:
    window_start: dt.date
    window_end: dt.date
    source: str
    summary: str
    suggestions: list[dict] = field(default_factory=list)
    fallback_reason: str | None = None


def _trend(daily_values: list[float]) -> str:
    """Compare the last 3 days with the days before them."""
    if len(daily_values) < 6:
        return "unknown"
    recent = sum(daily_values[-3:]) / 3
    earlier_days = daily_values[:-3]
    earlier = sum(earlier_days) / len(earlier_days)
    if earlier == 0:
        return "unknown"
    ratio = recent / earlier
    if ratio > 1.15:
        return "up"
    if ratio < 0.85:
        return "down"
    return "flat"


def parse_llm_response(text: str, candidates_by_id: dict[str, rules_module.Candidate], max_items: int) -> tuple[str, list[dict]]:
    """Validate the model's JSON reply. Raises ValueError if it is not usable."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise ValueError("model reply was not valid JSON") from err
    if not isinstance(data, dict) or not isinstance(data.get("suggestions"), list):
        raise ValueError("model reply had no suggestions list")

    suggestions, seen = [], set()
    for item in data["suggestions"]:
        if not isinstance(item, dict):
            continue
        cid = item.get("candidate_id")
        title, message = item.get("title"), item.get("message")
        if cid not in candidates_by_id or cid in seen:
            continue
        if not isinstance(title, str) or not isinstance(message, str) or not title.strip() or not message.strip():
            continue
        seen.add(cid)
        candidate = candidates_by_id[cid]
        suggestions.append(
            {
                "candidate_id": cid,
                "title": title.strip()[:80],
                "message": message.strip()[:300],
                "category": candidate.category,
                "weekly_saving_kg_co2e": candidate.weekly_saving_kg_co2e,
            }
        )
        if len(suggestions) == max_items:
            break
    if not suggestions:
        raise ValueError("model reply had no valid suggestions")

    summary = data.get("summary")
    summary = summary.strip()[:400] if isinstance(summary, str) else ""
    return summary, suggestions


class RecommendationEngine:
    def __init__(
        self,
        storage: Storage,
        calculator: EmissionCalculator,
        gemini: GeminiClient | None = None,
        max_suggestions: int = 3,
    ):
        self.storage = storage
        self.calculator = calculator
        self.gemini = gemini
        self.max_suggestions = max_suggestions
        self.rules = rules_module.load_rules()

    # ------------------------------------------------------------------
    def recommend(self, user: dict, end: dt.date, days: int = 7, use_ai: bool = True) -> RecommendationResult:
        start = end - dt.timedelta(days=days - 1)
        user_id = user["user_id"]
        daily = self.storage.daily_totals(user_id, start, end)
        total = sum(daily.values())

        if total == 0:
            return RecommendationResult(
                window_start=start,
                window_end=end,
                source="rules",
                summary=f"No activity logged in the last {days} days yet.",
                suggestions=[
                    {"candidate_id": None, "title": tip["title"], "message": tip["message"],
                     "category": tip["category"], "weekly_saving_kg_co2e": None}
                    for tip in rules_module.starter_tips(self.rules)
                ],
            )

        by_category = self.storage.category_totals(user_id, start, end)
        type_totals = self.storage.type_totals(user_id, start, end)
        day_values = [daily.get((start + dt.timedelta(days=i)).isoformat(), 0.0) for i in range(days)]
        summary = {
            "region": user["region"],
            "window_days": days,
            "days_with_activity": len(daily),
            "total_co2e_kg": round(total, 1),
            "average_daily_co2e_kg": round(total / days, 1),
            "by_category_kg": {k: round(v, 1) for k, v in by_category.items()},
            "top_sources": [
                {"activity": r["label"], "amount": round(r["quantity"], 1), "unit": r["unit"], "co2e_kg": round(r["co2e_kg"], 1)}
                for r in type_totals[:5]
            ],
            "trend_last_3_days_vs_earlier": _trend(day_values),
        }

        candidates = rules_module.build_candidates(type_totals, days, user["region"], self.calculator, self.rules)
        rule_summary = self._rule_summary(summary)

        if not candidates:
            return RecommendationResult(start, end, "rules", rule_summary, [])

        fallback_reason = None
        if not use_ai:
            fallback_reason = "AI was switched off for this request"
        elif self.gemini is None:
            fallback_reason = "GEMINI_API_KEY is not set"
        else:
            try:
                return self._ask_model(start, end, summary, candidates, rule_summary)
            except (GeminiError, ValueError) as err:
                fallback_reason = f"AI step failed ({err}); used rule-based wording"

        return RecommendationResult(start, end, "rules", rule_summary, self._rule_suggestions(candidates), fallback_reason)

    # ------------------------------------------------------------------
    def _ask_model(self, start, end, summary, candidates, rule_summary) -> RecommendationResult:
        shortlist = candidates[:MAX_CANDIDATES_TO_MODEL]
        payload = build_user_payload(
            summary,
            [
                {
                    "candidate_id": c.id,
                    "category": c.category,
                    "action": c.action,
                    "weekly_saving_kg_co2e": c.weekly_saving_kg_co2e,
                    "evidence": c.evidence,
                }
                for c in shortlist
            ],
        )
        text = self.gemini.generate_json(SYSTEM_INSTRUCTION, payload)
        by_id = {c.id: c for c in shortlist}
        ai_summary, suggestions = parse_llm_response(text, by_id, self.max_suggestions)
        return RecommendationResult(start, end, "gemini", ai_summary or rule_summary, suggestions)

    def _rule_suggestions(self, candidates: list[rules_module.Candidate]) -> list[dict]:
        return [
            {
                "candidate_id": c.id,
                "title": c.title,
                "message": f"{c.action} That could save about {c.weekly_saving_kg_co2e:g} kg CO2e a week.",
                "category": c.category,
                "weekly_saving_kg_co2e": c.weekly_saving_kg_co2e,
            }
            for c in candidates[: self.max_suggestions]
        ]

    @staticmethod
    def _rule_summary(summary: dict) -> str:
        top_category = next(iter(summary["by_category_kg"]), None)
        text = f"Over the last {summary['window_days']} days you averaged {summary['average_daily_co2e_kg']} kg CO2e a day"
        if top_category:
            text += f", mostly from {CATEGORY_NAMES.get(top_category, top_category)}"
        text += "."
        trend = summary["trend_last_3_days_vs_earlier"]
        if trend == "up":
            text += " The last few days were higher than the days before."
        elif trend == "down":
            text += " The last few days were lower than the days before."
        return text
