from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..scoring.engine import compute_scoring
from ..scoring.money import churn_probability, service_value_cents
from ..scoring.recompute import _load_snapshot, load_settings


def build_timeline(engine: Engine) -> dict:
    snapshot = _load_snapshot(engine)
    settings, _ = load_settings(engine)
    scoring = compute_scoring(snapshot, settings)
    scoring_by_service = {item.service_id: item for item in scoring.services}
    services_by_id = {service.id: service for service in snapshot.services}
    observed: dict[date, int] = defaultdict(int)
    estimated: dict[date, int] = defaultdict(int)
    forecast: dict[date, float] = defaultdict(float)

    with engine.connect() as connection:
        events = connection.execute(
            text(
                """
                SELECT service_id, changed_at FROM app.service_status_events
                WHERE new_status IN ('deleted', 'blocked')
                """
            )
        ).all()
    for service_id, changed_at in events:
        service = services_by_id.get(service_id)
        if service:
            observed[changed_at.date()] += service_value_cents(service, settings)

    for service in snapshot.services:
        if service.status == "deleted":
            estimated[(service.expires_at + timedelta(days=5)).date()] += service_value_cents(
                service, settings
            )
        if service.status not in {"active", "suspended", "prolong_wait"}:
            continue
        days_left = (service.expires_at - scoring.as_of).total_seconds() / 86400
        if 0 <= days_left <= 30:
            service_score = scoring_by_service.get(service.id)
            if service_score and service_score.score is not None:
                forecast[service.expires_at.date()] += churn_probability(
                    service_score.score, settings
                )

    as_of_date = scoring.as_of.date()
    series = [
        _series("observed", observed),
        _series("estimated", estimated),
        _series("forecast", forecast),
    ]
    return {"asOf": scoring.as_of, "asOfDate": as_of_date, "series": series}


def _series(series_type: str, points: dict[date, int | float]) -> dict:
    return {
        "type": series_type,
        "points": [
            {"date": day, "value": value}
            for day, value in sorted(points.items())
        ],
    }