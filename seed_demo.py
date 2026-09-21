"""Create a demo user with a week of realistic activity so you can try the API.

    python scripts/seed_demo.py
    uvicorn ecopulse.main:create_app --factory --reload
    curl "http://127.0.0.1:8000/users/demo/recommendations"
"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ecopulse.config import load_settings  # noqa: E402
from ecopulse.services import build_services  # noqa: E402

USER_ID = "demo"
REGION = "IN"

# One entry per day, oldest first: (activity_type, quantity)
WEEK = [
    [("car_petrol", 18), ("electricity_home", 9.0), ("meal_vegetarian", 2), ("meal_chicken", 1), ("lpg_cooking", 0.4), ("waste_general", 0.6)],
    [("car_petrol", 14), ("electricity_home", 8.5), ("meal_vegetarian", 3), ("lpg_cooking", 0.4), ("waste_general", 0.5), ("bus", 5)],
    [("car_petrol", 22), ("electricity_home", 9.5), ("meal_vegetarian", 2), ("meal_chicken", 1), ("lpg_cooking", 0.4), ("waste_general", 0.6)],
    [("car_petrol", 12), ("electricity_home", 10.0), ("meal_vegetarian", 3), ("lpg_cooking", 0.3), ("waste_general", 0.5), ("walk_cycle", 2)],
    [("car_petrol", 25), ("electricity_home", 9.0), ("meal_vegetarian", 2), ("meal_beef", 1), ("lpg_cooking", 0.4), ("waste_general", 0.7)],
    [("car_petrol", 8), ("electricity_home", 11.0), ("meal_vegetarian", 2), ("meal_chicken", 1), ("lpg_cooking", 0.5), ("waste_general", 0.8)],
    [("electricity_home", 12.0), ("meal_vegetarian", 2), ("meal_beef", 1), ("lpg_cooking", 0.5), ("waste_general", 0.9), ("auto_rickshaw", 6)],
]


def main() -> None:
    services = build_services(load_settings())
    services.storage.upsert_user(USER_ID, REGION)
    today = dt.date.today()
    for index, activities in enumerate(WEEK):
        day = today - dt.timedelta(days=len(WEEK) - 1 - index)
        items = [(services.calculator.estimate(kind, qty, REGION), None) for kind, qty in activities]
        services.storage.add_activities(USER_ID, day, items)
    print(f"Seeded user '{USER_ID}' (region {REGION}) with {len(WEEK)} days of activity in {services.settings.db_path}")


if __name__ == "__main__":
    main()
