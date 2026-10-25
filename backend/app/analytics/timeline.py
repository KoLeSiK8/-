from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..scoring.money import churn_probability
from ..scoring.recompute import load_settings

FORECAST_DAYS = 30


def build_timeline(engine: Engine) -> dict:

    settings, _ = load_settings(engine)
    observed: dict[date, float] = defaultdict(float)
    estimated: dict[date, float] = defaultdict(float)
    forecast: dict[date, float] = defaultdict(float)

    with engine.connect() as connection:
        as_of = connection.execute(
            text("SELECT as_of FROM app.score_summary WHERE id = 1")
        ).scalar()
        events = connection.execute(
            text(
                """
                SELECT DISTINCT service_id, changed_at::date AS day
                FROM app.service_status_events
                WHERE new_status IN ('deleted', 'blocked')
                  AND old_status NOT IN ('deleted', 'blocked')
                """
            )
        ).all()
        services = connection.execute(
            text(
                """
                SELECT services.status, services."expiresAt" AS expires_at, scores.score
                FROM public.services AS services
                LEFT JOIN app.service_scores AS scores ON scores.service_id = services.id
                """
            )
        ).mappings().all()

    as_of = as_of or datetime.now(timezone.utc)
    for _, day in events:
        observed[day] += 1

    for service in services:
        if service["status"] == "deleted":
            estimated[(service["expires_at"] + timedelta(days=5)).date()] += 1
            continue
        if service["status"] not in {"active", "suspended", "prolong_wait"}:
            continue
        if service["score"] is None:
            continue
        days_left = (service["expires_at"] - as_of).total_seconds() / 86400
        if 0 <= days_left <= FORECAST_DAYS:
            forecast[service["expires_at"].date()] += churn_probability(
                service["score"], settings
            )

    return {
        "asOf": as_of,
        "asOfDate": as_of.date(),
        "unit": "services",
        "series": [
            _series("observed", observed),
            _series("estimated", estimated),
            _series("forecast", forecast),
        ],
    }


def _series(series_type: str, points: dict[date, float]) -> dict:
    return {
        "type": series_type,
        "points": [
            {"date": day, "value": round(value, 4)}
            for day, value in sorted(points.items())
        ],
    }
