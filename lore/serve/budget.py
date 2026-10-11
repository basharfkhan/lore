"""Daily spending cap and per-visitor rate limit for the public demo.

Every live question costs real money, so the service refuses new questions once the day's
spend reaches the cap. The count has to survive restarts: a free host puts the service to sleep
and wakes it with an empty disk, which would silently reset a counter kept in a file. When
DATABASE_URL is set the count lives in Postgres; the file store is for local development.

The cap is checked before a question starts and the actual cost is added afterwards, so a day
can overshoot by at most the questions already in flight.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from lore.paths import DATA_DIR

DAILY_CAP_USD = float(os.environ.get("LORE_DAILY_CAP_USD", "1.00"))
QUESTIONS_PER_HOUR = int(os.environ.get("LORE_QUESTIONS_PER_HOUR", "6"))


def today() -> str:
    return datetime.now(UTC).date().isoformat()


class FileSpend:
    def __init__(self, path: Path = DATA_DIR / "interim" / "spend.json"):
        self.path = path
        self.lock = threading.Lock()

    def _read(self) -> dict[str, float]:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def spent_today(self) -> float:
        with self.lock:
            return self._read().get(today(), 0.0)

    def add(self, usd: float) -> None:
        with self.lock:
            data = self._read()
            data[today()] = round(data.get(today(), 0.0) + usd, 6)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data), encoding="utf-8")


class PostgresSpend:
    def __init__(self, url: str):
        import psycopg  # only needed when a database is configured

        self.psycopg = psycopg
        self.url = url
        with psycopg.connect(url) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS lore_spend "
                "(day date PRIMARY KEY, usd numeric NOT NULL DEFAULT 0)"
            )

    def spent_today(self) -> float:
        with self.psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT usd FROM lore_spend WHERE day = %s", (today(),)).fetchone()
        return float(row[0]) if row else 0.0

    def add(self, usd: float) -> None:
        with self.psycopg.connect(self.url) as conn:
            conn.execute(
                "INSERT INTO lore_spend (day, usd) VALUES (%s, %s) "
                "ON CONFLICT (day) DO UPDATE SET usd = lore_spend.usd + EXCLUDED.usd",
                (today(), usd),
            )


def spend_store():
    url = os.environ.get("DATABASE_URL")
    return PostgresSpend(url) if url else FileSpend()


class RateLimiter:
    """At most ``limit`` questions per visitor in any rolling hour, kept in memory."""

    def __init__(self, limit: int = QUESTIONS_PER_HOUR, window: float = 3600):
        self.limit = limit
        self.window = window
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self.lock:
            recent = [t for t in self.hits.get(key, []) if now - t < self.window]
            if len(recent) >= self.limit:
                self.hits[key] = recent
                return False
            self.hits[key] = [*recent, now]
            return True
