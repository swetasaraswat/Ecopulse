"""SQLite storage for users and logged activities.

Every operation opens its own short-lived connection, which keeps things safe
under FastAPI's thread pool without any extra locking.
"""

import datetime as dt
import sqlite3
from collections.abc import Sequence
from contextlib import closing, contextmanager

from .emissions import EmissionEstimate

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    region     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    activity_date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    category      TEXT NOT NULL,
    label         TEXT NOT NULL,
    quantity      REAL NOT NULL,
    unit          TEXT NOT NULL,
    factor        REAL NOT NULL,
    co2e_kg       REAL NOT NULL,
    region_used   TEXT,
    grid_fallback INTEGER NOT NULL DEFAULT 0,
    confidence    TEXT NOT NULL,
    notes         TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_user_date ON activities(user_id, activity_date);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: str):
        self.path = path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # users -----------------------------------------------------------------
    def upsert_user(self, user_id: str, region: str) -> dict:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (user_id, region, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET region = excluded.region",
                (user_id, region, _now()),
            )
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row)

    def get_user(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    # activities ------------------------------------------------------------
    def add_activities(
        self,
        user_id: str,
        day: dt.date,
        items: Sequence[tuple[EmissionEstimate, str | None]],
    ) -> list[int]:
        ids = []
        with self._connect() as conn:
            for estimate, notes in items:
                cursor = conn.execute(
                    "INSERT INTO activities (user_id, activity_date, activity_type, category, label, "
                    "quantity, unit, factor, co2e_kg, region_used, grid_fallback, confidence, notes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id, day.isoformat(), estimate.activity_type, estimate.category, estimate.label,
                        estimate.quantity, estimate.unit, estimate.factor_kg_co2e_per_unit, estimate.co2e_kg,
                        estimate.region_used, int(estimate.grid_fallback), estimate.confidence, notes, _now(),
                    ),
                )
                ids.append(cursor.lastrowid)
        return ids

    def activities_on(self, user_id: str, day: dt.date) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM activities WHERE user_id = ? AND activity_date = ? ORDER BY id",
                (user_id, day.isoformat()),
            ).fetchall()
        return [dict(r) for r in rows]

    def daily_totals(self, user_id: str, start: dt.date, end: dt.date) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT activity_date, SUM(co2e_kg) AS total FROM activities "
                "WHERE user_id = ? AND activity_date BETWEEN ? AND ? GROUP BY activity_date",
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return {r["activity_date"]: r["total"] for r in rows}

    def category_totals(self, user_id: str, start: dt.date, end: dt.date) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, SUM(co2e_kg) AS total FROM activities "
                "WHERE user_id = ? AND activity_date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC",
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return {r["category"]: r["total"] for r in rows}

    def type_totals(self, user_id: str, start: dt.date, end: dt.date) -> list[dict]:
        """Quantity and emissions per activity type, biggest emitters first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT activity_type, label, unit, SUM(quantity) AS quantity, SUM(co2e_kg) AS co2e_kg "
                "FROM activities WHERE user_id = ? AND activity_date BETWEEN ? AND ? "
                "GROUP BY activity_type, label, unit ORDER BY co2e_kg DESC",
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [dict(r) for r in rows]
