import datetime as dt

from ecopulse.emissions import EmissionCalculator, FactorStore
from ecopulse.storage import Storage


def test_user_upsert_updates_region(tmp_path):
    storage = Storage(str(tmp_path / "s.db"))
    storage.upsert_user("sweta", "IN")
    updated = storage.upsert_user("sweta", "GB")
    assert updated["region"] == "GB"
    assert storage.get_user("nobody") is None


def test_totals_by_day_category_and_type(tmp_path):
    storage = Storage(str(tmp_path / "s.db"))
    calc = EmissionCalculator(FactorStore())
    storage.upsert_user("u", "IN")
    day1, day2 = dt.date(2026, 9, 14), dt.date(2026, 9, 15)
    storage.add_activities("u", day1, [(calc.estimate("car_petrol", 10, "IN"), None), (calc.estimate("meal_chicken", 2, "IN"), "lunch")])
    storage.add_activities("u", day2, [(calc.estimate("car_petrol", 20, "IN"), None)])

    daily = storage.daily_totals("u", day1, day2)
    assert set(daily) == {"2026-09-14", "2026-09-15"}
    assert daily["2026-09-15"] > daily["2026-09-14"] - 5

    categories = storage.category_totals("u", day1, day2)
    assert set(categories) == {"transport", "food"}

    types = storage.type_totals("u", day1, day2)
    petrol = next(t for t in types if t["activity_type"] == "car_petrol")
    assert petrol["quantity"] == 30

    # a window that excludes day 2
    assert storage.daily_totals("u", day1, day1).keys() == {"2026-09-14"}
