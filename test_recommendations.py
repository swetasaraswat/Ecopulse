import datetime as dt
import json

import pytest

from ecopulse.recommendations import rules
from ecopulse.recommendations.engine import RecommendationEngine, parse_llm_response
from ecopulse.recommendations.gemini_client import GeminiError

END = dt.date(2026, 9, 20)


class FakeGemini:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def generate_json(self, system_instruction, user_payload):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


def seed_week(services, user_id="u", region="IN"):
    services.storage.upsert_user(user_id, region)
    for offset in range(7):
        day = END - dt.timedelta(days=offset)
        items = [
            services.calculator.estimate("car_petrol", 20, region),
            services.calculator.estimate("electricity_home", 8, region),
            services.calculator.estimate("meal_chicken", 1, region),
        ]
        services.storage.add_activities(user_id, day, [(i, None) for i in items])
    return services.storage.get_user(user_id)


def engine_with(services, gemini=None):
    return RecommendationEngine(services.storage, services.calculator, gemini)


def test_candidate_saving_is_calculated_from_the_factor_model(services):
    seed_week(services)
    types = services.storage.type_totals("u", END - dt.timedelta(days=6), END)
    candidates = rules.build_candidates(types, 7, "IN", services.calculator)
    bus = next(c for c in candidates if c.id == "car_petrol_to_bus")
    # 140 km of car in the week, 30% moved to a bus: 42 km * (0.165 - 0.10)
    assert bus.weekly_saving_kg_co2e == pytest.approx(42 * (0.165 - 0.10), abs=0.02)
    assert candidates == sorted(candidates, key=lambda c: c.weekly_saving_kg_co2e, reverse=True)


def test_rules_only_when_no_ai_configured(services):
    user = seed_week(services)
    result = engine_with(services).recommend(user, END)
    assert result.source == "rules"
    assert "GEMINI_API_KEY" in result.fallback_reason
    assert 1 <= len(result.suggestions) <= 3
    assert all(s["weekly_saving_kg_co2e"] > 0 for s in result.suggestions)


def test_no_history_gives_starter_tips(services):
    services.storage.upsert_user("empty", "IN")
    result = engine_with(services).recommend(services.storage.get_user("empty"), END)
    assert result.source == "rules"
    assert len(result.suggestions) == 3
    assert all(s["weekly_saving_kg_co2e"] is None for s in result.suggestions)


def test_valid_model_reply_is_used_but_savings_stay_grounded(services):
    user = seed_week(services)
    reply = json.dumps({
        "summary": "A steady week.",
        "suggestions": [
            {"candidate_id": "car_petrol_to_bus", "title": "Bus for a few trips", "message": "Try the bus twice this week.",
             "weekly_saving_kg_co2e": 999},  # the model must not be able to change the number
        ],
    })
    fake = FakeGemini(reply)
    result = engine_with(services, fake).recommend(user, END)
    assert result.source == "gemini"
    assert result.suggestions[0]["weekly_saving_kg_co2e"] < 10
    assert result.summary == "A steady week."
    assert fake.calls == 1


def test_invented_candidate_ids_are_dropped(services):
    user = seed_week(services)
    reply = json.dumps({"summary": "x", "suggestions": [
        {"candidate_id": "made_up", "title": "t", "message": "m"},
        {"candidate_id": "car_petrol_to_bus", "title": "Real one", "message": "m"},
    ]})
    result = engine_with(services, FakeGemini(reply)).recommend(user, END)
    assert [s["candidate_id"] for s in result.suggestions] == ["car_petrol_to_bus"]


@pytest.mark.parametrize("bad_reply", ["not json at all", json.dumps({"suggestions": []}), json.dumps({"suggestions": [{"candidate_id": "nope"}]})])
def test_unusable_model_reply_falls_back_to_rules(services, bad_reply):
    user = seed_week(services)
    result = engine_with(services, FakeGemini(bad_reply)).recommend(user, END)
    assert result.source == "rules"
    assert result.fallback_reason
    assert result.suggestions


def test_gemini_error_falls_back_to_rules(services):
    user = seed_week(services)
    result = engine_with(services, FakeGemini(error=GeminiError("HTTP 500"))).recommend(user, END)
    assert result.source == "rules"
    assert "HTTP 500" in result.fallback_reason


def test_ai_can_be_switched_off_per_request(services):
    user = seed_week(services)
    fake = FakeGemini("{}")
    result = engine_with(services, fake).recommend(user, END, use_ai=False)
    assert result.source == "rules"
    assert fake.calls == 0


def test_parse_strips_markdown_fences():
    candidate = rules.Candidate("a", "T", "act", "food", 1.0, "ev")
    text = '```json\n{"summary": "s", "suggestions": [{"candidate_id": "a", "title": "T", "message": "M"}]}\n```'
    summary, suggestions = parse_llm_response(text, {"a": candidate}, 3)
    assert summary == "s" and suggestions[0]["candidate_id"] == "a"
